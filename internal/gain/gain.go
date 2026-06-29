// Package gain computes the agentic-cfg performance readout — "what is this
// config actually saving?" — from Claude Code session transcripts.
//
// It reads the JSONL transcripts Claude Code writes under
// ~/.claude/projects/**/<session>.jsonl (read-only) and reports, in aggregate:
// token volume, the token-weighted prompt-cache hit rate (the dominant
// token-cost lever), the input-token cost the cache is avoiding (the "gain"),
// the subagent share (context isolated off the main thread), and an estimated
// cost. It is the built-in, dependency-free counterpart to telemetry/report.py
// and deliberately mirrors that script's parsing so the two agree.
//
// Surfaced via `agentic gain`. Pure stdlib, no network.
package gain

import (
	"bufio"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

// rate is USD per 1M tokens. Mirrors telemetry/report.py PRICING — keep the two
// in sync. cache_read ~= 0.1x input, cache_5m ~= 1.25x, cache_1h ~= 2x, per
// Anthropic's published multipliers. Cost is for relative comparison, not a bill.
type rate struct{ in, cacheRead, cache5m, cache1h, out float64 }

var pricing = []struct {
	key string
	r   rate
}{
	{"opus", rate{15.0, 1.5, 18.75, 30.0, 75.0}},
	{"sonnet", rate{3.0, 0.3, 3.75, 6.0, 15.0}},
	{"haiku", rate{1.0, 0.1, 1.25, 2.0, 5.0}},
}

func ratesFor(model string) rate {
	m := strings.ToLower(model)
	for _, p := range pricing {
		if strings.Contains(m, p.key) {
			return p.r
		}
	}
	return pricing[0].r // default: opus
}

// Bucket is a token tally for one context (main thread or subagent sidechain).
type Bucket struct {
	Input      int `json:"input"`
	Output     int `json:"output"`
	CacheRead  int `json:"cache_read"`
	CacheWrite int `json:"cache_write"`
}

func (b Bucket) totalInput() int { return b.Input + b.CacheRead + b.CacheWrite }

// Session is the aggregated usage of one transcript file.
type Session struct {
	ID             string         `json:"session_id"`
	Project        string         `json:"project"`
	Branch         string         `json:"git_branch"`
	Models         map[string]int `json:"models"`
	AssistantTurns int            `json:"assistant_turns"`
	Main           Bucket         `json:"main"`
	Sub            Bucket         `json:"sub"`
	Cost           float64        `json:"est_cost_usd"` // actual, incl. output
	InputCostGross float64        `json:"-"`            // counterfactual: total input billed at fresh rate
	InputCostReal  float64        `json:"-"`            // actual input-side cost (input+cache)
}

// TotalInput is fresh + cache-read + cache-write across both buckets. This is the
// denominator of the cache hit rate, matching telemetry/report.py.
func (s *Session) TotalInput() int { return s.Main.totalInput() + s.Sub.totalInput() }

// CacheRead is cache-served input across both buckets.
func (s *Session) CacheRead() int { return s.Main.CacheRead + s.Sub.CacheRead }

// SubInput is total input attributable to subagent sidechains.
func (s *Session) SubInput() int { return s.Sub.totalInput() }

// CacheHitRate is cache_read / total_input (0 when there is no input).
func (s *Session) CacheHitRate() float64 {
	ti := s.TotalInput()
	if ti == 0 {
		return 0
	}
	return float64(s.CacheRead()) / float64(ti)
}

// ---- parsing ----

type tRecord struct {
	Type        string    `json:"type"`
	IsSidechain bool      `json:"isSidechain"`
	SessionID   string    `json:"sessionId"`
	Cwd         string    `json:"cwd"`
	GitBranch   string    `json:"gitBranch"`
	Message     *tMessage `json:"message"`
}

type tMessage struct {
	ID    string  `json:"id"`
	Model string  `json:"model"`
	Usage *tUsage `json:"usage"`
}

type tUsage struct {
	InputTokens              int `json:"input_tokens"`
	OutputTokens             int `json:"output_tokens"`
	CacheReadInputTokens     int `json:"cache_read_input_tokens"`
	CacheCreationInputTokens int `json:"cache_creation_input_tokens"`
	CacheCreation            *struct {
		Ephemeral1h int `json:"ephemeral_1h_input_tokens"`
		Ephemeral5m int `json:"ephemeral_5m_input_tokens"`
	} `json:"cache_creation"`
}

// ParseLines reads a transcript stream and returns the aggregated Session, or
// nil if the stream carried no usage-bearing assistant turns. Malformed lines
// are skipped (legible degradation), never fatal. Claude Code repeats the
// message-level usage on every content-block record, so usage is counted once
// per message.id to avoid inflating tokens and cost.
func ParseLines(r io.Reader) (*Session, error) {
	s := &Session{Models: map[string]int{}}
	seen := map[string]bool{}
	sc := bufio.NewScanner(r)
	sc.Buffer(make([]byte, 0, 1024*1024), 64*1024*1024) // transcript lines can be large
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" {
			continue
		}
		var rec tRecord
		if err := json.Unmarshal([]byte(line), &rec); err != nil {
			continue // skip malformed line, keep going
		}
		if s.ID == "" {
			s.ID = rec.SessionID
		}
		if s.Project == "" && rec.Cwd != "" {
			s.Project = filepath.Base(rec.Cwd)
		}
		if s.Branch == "" {
			s.Branch = rec.GitBranch
		}
		if rec.Type != "assistant" || rec.Message == nil || rec.Message.Usage == nil {
			continue
		}
		if id := rec.Message.ID; id != "" {
			if seen[id] {
				continue
			}
			seen[id] = true
		}
		s.addUsage(rec)
	}
	if err := sc.Err(); err != nil {
		return nil, err
	}
	if s.AssistantTurns == 0 {
		return nil, nil
	}
	return s, nil
}

func (s *Session) addUsage(rec tRecord) {
	u := rec.Message.Usage
	s.AssistantTurns++
	if rec.Message.Model != "" {
		s.Models[rec.Message.Model]++
	}
	cw1h, cw5m := 0, 0
	if cc := u.CacheCreation; cc != nil {
		cw1h, cw5m = cc.Ephemeral1h, cc.Ephemeral5m
	}
	if cw1h+cw5m == 0 && u.CacheCreationInputTokens > 0 { // older records, no breakdown
		cw5m = u.CacheCreationInputTokens
	}
	b := &s.Main
	if rec.IsSidechain {
		b = &s.Sub
	}
	b.Input += u.InputTokens
	b.Output += u.OutputTokens
	b.CacheRead += u.CacheReadInputTokens
	b.CacheWrite += u.CacheCreationInputTokens

	r := ratesFor(rec.Message.Model)
	inCost := float64(u.InputTokens)*r.in + float64(u.CacheReadInputTokens)*r.cacheRead +
		float64(cw1h)*r.cache1h + float64(cw5m)*r.cache5m
	s.InputCostReal += inCost / 1e6
	// Counterfactual: every input/cache token billed at the fresh input rate.
	gross := float64(u.InputTokens+u.CacheReadInputTokens+u.CacheCreationInputTokens) * r.in
	s.InputCostGross += gross / 1e6
	s.Cost += (inCost + float64(u.OutputTokens)*r.out) / 1e6
}

// ParseFile parses one transcript file. Returns (nil, nil) for a file with no
// usable assistant turns (matching telemetry/report.py).
func ParseFile(path string) (*Session, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	s, err := ParseLines(f)
	if err != nil || s == nil {
		return s, err
	}
	if s.ID == "" {
		s.ID = strings.TrimSuffix(filepath.Base(path), ".jsonl")
	}
	if s.Project == "" {
		s.Project = filepath.Base(filepath.Dir(path))
	}
	return s, nil
}

// Collect parses every transcript under root (newest first by mtime), optionally
// filtered by a project/dir substring, and returns at most `last` sessions.
func Collect(root, project string, last int) ([]*Session, error) {
	var files []string
	err := filepath.WalkDir(root, func(p string, d os.DirEntry, err error) error {
		if err != nil {
			return nil // skip unreadable subtrees rather than abort
		}
		if !d.IsDir() && strings.HasSuffix(p, ".jsonl") {
			files = append(files, p)
		}
		return nil
	})
	if err != nil {
		return nil, err
	}
	sort.Slice(files, func(i, j int) bool {
		fi, e1 := os.Stat(files[i])
		fj, e2 := os.Stat(files[j])
		if e1 != nil || e2 != nil {
			return files[i] > files[j]
		}
		return fi.ModTime().After(fj.ModTime())
	})
	var out []*Session
	for _, f := range files {
		s, err := ParseFile(f)
		if err != nil || s == nil {
			continue
		}
		if project != "" && !strings.Contains(strings.ToLower(s.Project+" "+filepath.Base(filepath.Dir(f))), strings.ToLower(project)) {
			continue
		}
		out = append(out, s)
		if last > 0 && len(out) >= last {
			break
		}
	}
	return out, nil
}

// Report is the aggregate gain readout across a set of sessions.
type Report struct {
	Sessions       int     `json:"sessions"`
	Input          int     `json:"input_fresh"`
	CacheRead      int     `json:"cache_read"`
	CacheWrite     int     `json:"cache_write"`
	Output         int     `json:"output"`
	TotalInput     int     `json:"total_input"`
	SubInput       int     `json:"subagent_input"`
	CacheHitRate   float64 `json:"cache_hit_rate"`
	SubagentShare  float64 `json:"subagent_share"`
	InputCostSaved float64 `json:"input_cost_saved_usd"`
	InputSavedPct  float64 `json:"input_cost_saved_pct"`
	EstCostUSD     float64 `json:"est_cost_usd"`
}

// Aggregate folds sessions into the token-weighted Report.
func Aggregate(sessions []*Session) Report {
	var r Report
	var gross, real float64
	for _, s := range sessions {
		r.Input += s.Main.Input + s.Sub.Input
		r.CacheRead += s.CacheRead()
		r.CacheWrite += s.Main.CacheWrite + s.Sub.CacheWrite
		r.Output += s.Main.Output + s.Sub.Output
		r.TotalInput += s.TotalInput()
		r.SubInput += s.SubInput()
		r.EstCostUSD += s.Cost
		gross += s.InputCostGross
		real += s.InputCostReal
	}
	r.Sessions = len(sessions)
	if r.TotalInput > 0 {
		r.CacheHitRate = float64(r.CacheRead) / float64(r.TotalInput)
		r.SubagentShare = float64(r.SubInput) / float64(r.TotalInput)
	}
	r.InputCostSaved = gross - real
	if gross > 0 {
		r.InputSavedPct = (gross - real) / gross
	}
	return r
}

func fmtK(n int) string {
	switch {
	case n >= 1_000_000:
		return fmt.Sprintf("%.1fM", float64(n)/1e6)
	case n >= 1_000:
		return fmt.Sprintf("%.1fk", float64(n)/1e3)
	default:
		return fmt.Sprintf("%d", n)
	}
}

// Render writes the human-readable readout (or JSON) for a report.
func Render(w io.Writer, r Report, asJSON bool) {
	if asJSON {
		enc := json.NewEncoder(w)
		enc.SetIndent("", "  ")
		_ = enc.Encode(r)
		return
	}
	if r.Sessions == 0 {
		fmt.Fprintln(w, "No sessions matched — run some work first, then `agentic gain`.")
		return
	}
	verdict := "below the 80% floor — check cache hygiene (telemetry/gate.py, prompt-caching-playbook)"
	if r.CacheHitRate >= 0.80 {
		verdict = "healthy (≥ 80% floor)"
	}
	fmt.Fprintf(w, "agentic-cfg gain — over %d session(s)\n", r.Sessions)
	fmt.Fprintf(w, "  input (fresh)    : %s\n", fmtK(r.Input))
	fmt.Fprintf(w, "  cache read       : %s\n", fmtK(r.CacheRead))
	fmt.Fprintf(w, "  cache write      : %s\n", fmtK(r.CacheWrite))
	fmt.Fprintf(w, "  output           : %s\n", fmtK(r.Output))
	fmt.Fprintf(w, "  cache hit rate   : %.1f%%   (cache_read / total input) — %s\n", r.CacheHitRate*100, verdict)
	fmt.Fprintf(w, "  subagent share   : %.1f%%   (context isolated off the main thread)\n", r.SubagentShare*100)
	fmt.Fprintf(w, "  input cost saved : $%.2f  (%.0f%% of the would-be input bill, avoided by caching)\n", r.InputCostSaved, r.InputSavedPct*100)
	fmt.Fprintf(w, "  est. cost        : $%.2f  (approximate — verify rates vs current pricing)\n", r.EstCostUSD)
}

// Main is the `agentic gain` entry point.
func Main(args []string) int {
	fs := flag.NewFlagSet("gain", flag.ContinueOnError)
	root := fs.String("root", defaultRoot(), "transcript root (default: ~/.claude/projects)")
	last := fs.Int("last", 20, "number of most-recent sessions to include (0 = all)")
	project := fs.String("project", "", "filter by project/dir substring")
	asJSON := fs.Bool("json", false, "emit JSON instead of a table")
	fs.Usage = func() {
		fmt.Fprint(os.Stderr, "usage: agentic gain [--root DIR] [--last N] [--project SUBSTR] [--json]\n\n"+
			"Built-in performance readout from Claude Code transcripts: token volume,\n"+
			"prompt-cache hit rate, input cost avoided by caching, and subagent share.\n")
	}
	if err := fs.Parse(args); err != nil {
		return 2
	}
	if _, err := os.Stat(*root); err != nil {
		fmt.Fprintf(os.Stderr, "agentic gain: transcript root not found: %s\n", *root)
		return 2
	}
	sessions, err := Collect(*root, *project, *last)
	if err != nil {
		fmt.Fprintf(os.Stderr, "agentic gain: %v\n", err)
		return 1
	}
	Render(os.Stdout, Aggregate(sessions), *asJSON)
	return 0
}

func defaultRoot() string {
	home, err := os.UserHomeDir()
	if err != nil {
		return ".claude/projects"
	}
	return filepath.Join(home, ".claude", "projects")
}
