// Package gain computes a session token-economy readout from Claude Code
// transcripts: how the prompt cache and subagent isolation are shaping your
// token bill.
//
// Honesty note on attribution. The dollar figure this reports as "cache
// avoided" is what Anthropic's *prompt cache* saves versus re-sending the same
// context uncached. Prompt caching is a Claude **platform** feature — it works
// in any session, with or without agentic-cfg. So this is NOT a measure of what
// the config itself saves; agentic-cfg's lever here is narrow (cache-hygiene:
// keeping the prefix byte-stable so the platform cache stays warm — see the
// prompt-caching-playbook skill). To measure the config's *own* effect you need
// an A/B with the config on vs off (that is what evals/swe_bench.py does), not
// this readout. This command reports the actual input bill alongside the
// counterfactual so the avoided figure can't be mistaken for money pocketed.
//
// It reads the JSONL transcripts under ~/.claude/projects/**/<session>.jsonl
// (read-only) and reports, in aggregate: token volume, the token-weighted
// cache hit rate, the actual input-side cost, the cost the cache avoided vs an
// uncached baseline, the subagent share, and an estimated total cost. It is the
// built-in, dependency-free counterpart to telemetry/report.py and mirrors that
// script's parsing so the two agree.
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
	"regexp"
	"sort"
	"strconv"
	"strings"

	"github.com/Tsurai7/agentic-cfg/internal/hook"
)

// rate is USD per 1M tokens. Mirrors telemetry/report.py PRICING — keep the two
// in sync. cache_read = 0.1x input, cache_5m = 1.25x input, cache_1h = 2x input,
// per Anthropic's published multipliers. Rates cached from platform docs
// 2026-06-24 via the claude-api reference. Sonnet has introductory pricing
// ($2/$10) through 2026-08-31; the sticker $3/$15 is used here — these are
// estimates, not billing truth; verify before quoting dollars.
type rate struct{ in, cacheRead, cache5m, cache1h, out float64 }

var pricing = []struct {
	key string
	r   rate
}{
	{"fable", rate{10.0, 1.0, 12.5, 20.0, 50.0}},
	{"mythos", rate{10.0, 1.0, 12.5, 20.0, 50.0}},
	{"opus", rate{5.0, 0.5, 6.25, 10.0, 25.0}},
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
	return defaultRate() // default: opus
}

// knownModel reports whether model matches one of the pricing table's keys
// (same substring scan as ratesFor), so callers can flag estimates billed at
// the opus fallback rather than a rate actually keyed to the model.
func knownModel(model string) bool {
	m := strings.ToLower(model)
	for _, p := range pricing {
		if strings.Contains(m, p.key) {
			return true
		}
	}
	return false
}

func defaultRate() rate {
	for _, p := range pricing {
		if p.key == "opus" {
			return p.r
		}
	}
	return rate{}
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
	ID             string             `json:"session_id"`
	Project        string             `json:"project"`
	Branch         string             `json:"git_branch"`
	Models         map[string]int     `json:"models"`
	AssistantTurns int                `json:"assistant_turns"`
	Main           Bucket             `json:"main"`
	Sub            Bucket             `json:"sub"`
	PerModel       map[string]*Bucket `json:"-"`                  // tokens per concrete model id
	Cost           float64            `json:"est_cost_usd"`       // actual, incl. output
	InputCostGross float64            `json:"-"`                  // counterfactual: total input billed at fresh rate
	InputCostReal  float64            `json:"-"`                  // actual input-side cost (input+cache)
	Adoption       *AdoptionStats     `json:"adoption,omitempty"` // nil unless ParseOpts.Adoption is set
}

// AdoptionStats is the enforcement-coverage readout: how much Bash traffic the
// shell-guard actually wraps/denies, and how much the model reaches for
// ast-grep, lean-ctx, and GitNexus instead of native/raw tools. Collected only
// when ParseOpts.Adoption is set, so the default gain path stays cheap.
type AdoptionStats struct {
	BashTotal      int            `json:"bash_total"`
	ByDecision     map[string]int `json:"by_decision"`
	DeniesObserved int            `json:"denies_observed"`
	SgCalls        int            `json:"sg_calls"`
	GrepCalls      int            `json:"grep_calls"`
	CtxCalls       int            `json:"ctx_calls"`
	GitnexusCalls  int            `json:"gitnexus_calls"`
	NativeReads    int            `json:"native_reads"`
	NativeGreps    int            `json:"native_greps"`
}

func (a *AdoptionStats) add(o *AdoptionStats) {
	a.BashTotal += o.BashTotal
	for k, v := range o.ByDecision {
		a.ByDecision[k] += v
	}
	a.DeniesObserved += o.DeniesObserved
	a.SgCalls += o.SgCalls
	a.GrepCalls += o.GrepCalls
	a.CtxCalls += o.CtxCalls
	a.GitnexusCalls += o.GitnexusCalls
	a.NativeReads += o.NativeReads
	a.NativeGreps += o.NativeGreps
}

// sgCallRe matches an sg/ast-grep invocation as the command word.
var sgCallRe = regexp.MustCompile(`(^|[\s|;&])(sg|ast-grep)\s`)

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
	ID      string          `json:"id"`
	Model   string          `json:"model"`
	Usage   *tUsage         `json:"usage"`
	Content json.RawMessage `json:"content"` // string (plain text) or []tContentBlock; only the array form carries tool_use/tool_result
}

// tContentBlock is one message.content array entry, parsed loosely (type + the
// fields each block kind needs) since assistant tool_use and user tool_result
// blocks share the array but not a schema.
type tContentBlock struct {
	Type    string          `json:"type"`
	Name    string          `json:"name"`    // tool_use
	Input   json.RawMessage `json:"input"`   // tool_use
	Content json.RawMessage `json:"content"` // tool_result (string or block array); inspected as raw text
}

// contentBlocks parses message.content when it is an array, returning nil
// (not an error) when it is a plain string or absent.
func (m *tMessage) contentBlocks() []tContentBlock {
	if len(m.Content) == 0 || m.Content[0] != '[' {
		return nil
	}
	var blocks []tContentBlock
	_ = json.Unmarshal(m.Content, &blocks)
	return blocks
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

// ParseOpts controls optional, non-default collection during parsing.
type ParseOpts struct {
	Adoption bool // collect enforcement-coverage stats (AdoptionStats) — opt-in, extra scan cost
}

// ParseLines reads a transcript stream and returns the aggregated Session, or
// nil if the stream carried no usage-bearing assistant turns. Malformed lines
// are skipped (legible degradation), never fatal. Claude Code repeats the
// message-level usage on every content-block record, so usage is counted once
// per message.id to avoid inflating tokens and cost.
func ParseLines(r io.Reader) (*Session, error) {
	return ParseLinesOpts(r, ParseOpts{})
}

// ParseLinesOpts is ParseLines with optional adoption-stats collection.
func ParseLinesOpts(r io.Reader, opts ParseOpts) (*Session, error) {
	s := &Session{Models: map[string]int{}, PerModel: map[string]*Bucket{}}
	var adoption *AdoptionStats
	if opts.Adoption {
		adoption = &AdoptionStats{ByDecision: map[string]int{}}
	}
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
		if adoption != nil {
			scanAdoption(&rec, adoption)
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
		s.addUsage(&rec)
	}
	if err := sc.Err(); err != nil {
		return nil, err
	}
	if s.AssistantTurns == 0 {
		return nil, nil //nolint:nilnil // (nil, nil) is the documented "no usable session" signal
	}
	s.Adoption = adoption
	return s, nil
}

// scanAdoption tallies enforcement-coverage signals from one transcript
// record: assistant tool_use blocks (Bash classified via hook.Classify, plus
// sg/ast-grep, grep/rg, ctx_*, gitnexus, Read, Grep counts) and user
// tool_result blocks carrying the ast-grep deny reason text.
func scanAdoption(rec *tRecord, a *AdoptionStats) {
	if rec.Message == nil {
		return
	}
	blocks := rec.Message.contentBlocks()
	switch rec.Type {
	case "assistant":
		for _, b := range blocks {
			if b.Type != "tool_use" {
				continue
			}
			switch {
			case b.Name == "Bash":
				a.BashTotal++
				var input struct {
					Command string `json:"command"`
				}
				_ = json.Unmarshal(b.Input, &input)
				dec := string(hook.Classify(input.Command))
				a.ByDecision[dec]++
				if hook.GrepTokenRe.MatchString(input.Command) {
					a.GrepCalls++
				}
				if sgCallRe.MatchString(input.Command) {
					a.SgCalls++
				}
			case strings.HasPrefix(b.Name, "mcp__lean-ctx__"):
				a.CtxCalls++
			case strings.Contains(strings.ToLower(b.Name), "gitnexus"):
				a.GitnexusCalls++
			case b.Name == "Read":
				a.NativeReads++
			case b.Name == "Grep":
				a.NativeGreps++
			}
		}
	case "user":
		for _, b := range blocks {
			if b.Type != "tool_result" {
				continue
			}
			if strings.Contains(string(b.Content), astGrepReasonPrefix) {
				a.DeniesObserved++
			}
		}
	}
}

// astGrepReasonPrefix identifies an observed ast-grep deny in a tool_result,
// matching the hook's astGrepReason text (unexported there; kept short and
// exact enough to avoid false positives).
const astGrepReasonPrefix = "Use ast-grep for structural code search"

func (s *Session) addUsage(rec *tRecord) {
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

	model := rec.Message.Model
	if model == "" {
		model = "unknown"
	}
	pm := s.PerModel[model]
	if pm == nil {
		pm = &Bucket{}
		s.PerModel[model] = pm
	}
	pm.Input += u.InputTokens
	pm.Output += u.OutputTokens
	pm.CacheRead += u.CacheReadInputTokens
	pm.CacheWrite += u.CacheCreationInputTokens

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
	return ParseFileOpts(path, ParseOpts{})
}

// ParseFileOpts is ParseFile with optional adoption-stats collection.
func ParseFileOpts(path string, opts ParseOpts) (*Session, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	s, err := ParseLinesOpts(f, opts)
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
	return CollectOpts(root, project, last, ParseOpts{})
}

// CollectOpts is Collect with optional adoption-stats collection.
func CollectOpts(root, project string, last int, opts ParseOpts) ([]*Session, error) {
	var files []string
	err := filepath.WalkDir(root, func(p string, d os.DirEntry, err error) error {
		if err != nil {
			return nil //nolint:nilerr // intentionally skip unreadable subtrees rather than abort the walk
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
		s, err := ParseFileOpts(f, opts)
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
	Sessions       int            `json:"sessions"`
	Input          int            `json:"input_fresh"`
	CacheRead      int            `json:"cache_read"`
	CacheWrite     int            `json:"cache_write"`
	Output         int            `json:"output"`
	TotalInput     int            `json:"total_input"`
	SubInput       int            `json:"subagent_input"`
	CacheHitRate   float64        `json:"cache_hit_rate"`
	SubagentShare  float64        `json:"subagent_share"`
	InputCostReal  float64        `json:"input_cost_real_usd"`  // actual input-side bill (input + cache), what you paid
	InputCostSaved float64        `json:"input_cost_saved_usd"` // counterfactual: cost the cache avoided vs sending uncached
	InputSavedPct  float64        `json:"input_cost_saved_pct"`
	EstCostUSD     float64        `json:"est_cost_usd"`
	ByModel        []ModelStat    `json:"by_model"`
	Adoption       *AdoptionStats `json:"adoption,omitempty"` // nil unless --adoption was requested
}

// ModelStat is per-model token usage, for seeing whether cheap tiers carry the
// bulk of the work (the orchestration payoff).
type ModelStat struct {
	Model        string  `json:"model"`
	TotalInput   int     `json:"total_input"`
	CacheRead    int     `json:"cache_read"`
	Output       int     `json:"output"`
	CacheHitRate float64 `json:"cache_hit_rate"`
	InputShare   float64 `json:"input_share"`   // share of all total input
	Known        bool    `json:"known_pricing"` // false when billed at the default (opus) fallback rate
}

// Aggregate folds sessions into the token-weighted Report.
func Aggregate(sessions []*Session) Report {
	var r Report
	var gross, actual float64
	perModel := map[string]*Bucket{}
	for _, s := range sessions {
		r.Input += s.Main.Input + s.Sub.Input
		r.CacheRead += s.CacheRead()
		r.CacheWrite += s.Main.CacheWrite + s.Sub.CacheWrite
		r.Output += s.Main.Output + s.Sub.Output
		r.TotalInput += s.TotalInput()
		r.SubInput += s.SubInput()
		r.EstCostUSD += s.Cost
		gross += s.InputCostGross
		actual += s.InputCostReal
		if s.Adoption != nil {
			if r.Adoption == nil {
				r.Adoption = &AdoptionStats{ByDecision: map[string]int{}}
			}
			r.Adoption.add(s.Adoption)
		}
		for m, b := range s.PerModel {
			acc := perModel[m]
			if acc == nil {
				acc = &Bucket{}
				perModel[m] = acc
			}
			acc.Input += b.Input
			acc.Output += b.Output
			acc.CacheRead += b.CacheRead
			acc.CacheWrite += b.CacheWrite
		}
	}
	r.Sessions = len(sessions)
	if r.TotalInput > 0 {
		r.CacheHitRate = float64(r.CacheRead) / float64(r.TotalInput)
		r.SubagentShare = float64(r.SubInput) / float64(r.TotalInput)
	}
	for m, b := range perModel {
		ti := b.totalInput()
		if ti == 0 {
			continue // models that produced no input tokens (e.g. <synthetic>) add only noise
		}
		ms := ModelStat{Model: m, TotalInput: ti, CacheRead: b.CacheRead, Output: b.Output, Known: knownModel(m)}
		if ti > 0 {
			ms.CacheHitRate = float64(b.CacheRead) / float64(ti)
		}
		if r.TotalInput > 0 {
			ms.InputShare = float64(ti) / float64(r.TotalInput)
		}
		r.ByModel = append(r.ByModel, ms)
	}
	sort.Slice(r.ByModel, func(i, j int) bool { return r.ByModel[i].TotalInput > r.ByModel[j].TotalInput })
	r.InputCostReal = actual
	r.InputCostSaved = gross - actual
	if gross > 0 {
		r.InputSavedPct = (gross - actual) / gross
	}
	return r
}

// Gate evaluates a report against a minimum cache-hit-rate floor. It returns a
// verdict line and a process exit code: 0 = pass OR insufficient data (skip), 1 =
// regression. Mirrors telemetry/gate.py — token-weighted, and skips rather than
// fails when the sample is too small to judge, so cold-start noise can't trip it.
func Gate(r *Report, minRate float64, minTokens int) (verdict string, code int) {
	if r.TotalInput < minTokens {
		return fmt.Sprintf("SKIP: only %s input tokens (< %s) — too small to judge",
			fmtK(r.TotalInput), fmtK(minTokens)), 0
	}
	if r.CacheHitRate+1e-9 < minRate {
		return fmt.Sprintf("FAIL: cache hit rate %.1f%% < floor %.1f%% over %d session(s)",
			r.CacheHitRate*100, minRate*100, r.Sessions), 1
	}
	return fmt.Sprintf("PASS: cache hit rate %.1f%% >= floor %.1f%% over %d session(s)",
		r.CacheHitRate*100, minRate*100, r.Sessions), 0
}

func fmtK(n int) string {
	switch {
	case n >= 1_000_000:
		return fmt.Sprintf("%.1fM", float64(n)/1e6)
	case n >= 1_000:
		return fmt.Sprintf("%.1fk", float64(n)/1e3)
	default:
		return strconv.Itoa(n)
	}
}

// Render writes the human-readable readout (or JSON) for a report. With byModel,
// it appends a per-model token table — the orchestration signal (is the cheap
// tier carrying the bulk of the input?).
func Render(w io.Writer, r *Report, asJSON, byModel bool) {
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
	fmt.Fprintf(w, "agentic-cfg gain — session token economy over %d session(s)\n", r.Sessions)
	fmt.Fprintf(w, "  input (fresh)      : %s\n", fmtK(r.Input))
	fmt.Fprintf(w, "  cache read         : %s\n", fmtK(r.CacheRead))
	fmt.Fprintf(w, "  cache write        : %s\n", fmtK(r.CacheWrite))
	fmt.Fprintf(w, "  output             : %s\n", fmtK(r.Output))
	fmt.Fprintf(w, "  cache hit rate     : %.1f%%   (cache_read / total input) — %s\n", r.CacheHitRate*100, cacheVerdict(r.CacheHitRate))
	fmt.Fprintf(w, "  subagent share     : %.1f%%   (context isolated off the main thread)\n", r.SubagentShare*100)
	fmt.Fprintf(w, "  input bill (actual): $%.2f  (input + cache — what you actually paid)\n", r.InputCostReal)
	fmt.Fprintf(w, "  cache avoided      : $%.2f  (%.0f%% — vs re-sending the same context uncached)\n", r.InputCostSaved, r.InputSavedPct*100)
	fmt.Fprintf(w, "  est. total cost    : $%.2f  (incl. output; approximate — verify rates)\n", r.EstCostUSD)
	fmt.Fprintln(w, "  note: prompt caching is a Claude platform feature; agentic-cfg's lever is cache")
	fmt.Fprintln(w, "        hygiene (a warm, byte-stable prefix), not the avoided figure itself.")

	if byModel && len(r.ByModel) > 0 {
		fmt.Fprintf(w, "\nby model (total input share — is the cheap tier carrying the bulk?):\n")
		unknown := false
		for _, m := range r.ByModel {
			name := m.Model
			if !m.Known {
				name += "*"
				unknown = true
			}
			fmt.Fprintf(w, "  %-26s %6.1f%%   in %8s   hit %4.0f%%\n",
				name, m.InputShare*100, fmtK(m.TotalInput), m.CacheHitRate*100)
		}
		if unknown {
			fmt.Fprintln(w, "  * unknown model — billed at default (opus) rates in these estimates")
		}
	}

	if r.Adoption != nil {
		renderAdoption(w, r.Sessions, r.Adoption)
	}
}

// renderAdoption prints the enforcement-coverage block: how much Bash traffic
// the shell-guard wraps/denies/fails open on, and how much the model reaches
// for ast-grep/lean-ctx/GitNexus vs raw grep and native tools.
func renderAdoption(w io.Writer, sessions int, a *AdoptionStats) {
	fmt.Fprintf(w, "\nadoption — enforcement coverage over %d session(s):\n", sessions)
	total := a.BashTotal
	pct := func(n int) float64 {
		if total == 0 {
			return 0
		}
		return float64(n) / float64(total) * 100
	}
	wrapped := a.ByDecision[string(hook.DecisionWrap)]
	alreadyWrapped := a.ByDecision[string(hook.DecisionAlreadyWrapped)]
	complex := a.ByDecision[string(hook.DecisionFailOpenComplex)]
	assign := a.ByDecision[string(hook.DecisionFailOpenAssign)]
	equals := a.ByDecision[string(hook.DecisionFailOpenEquals)]
	failOpen := complex + assign + equals
	deny := a.ByDecision[string(hook.DecisionDenyGrepCode)]
	fmt.Fprintf(w, "  bash calls           : %d\n", total)
	fmt.Fprintf(w, "  wrapped (rtk/lean-ctx): %.1f%%   already-wrapped: %.1f%%\n", pct(wrapped), pct(alreadyWrapped))
	fmt.Fprintf(w, "  fail-open            : %.1f%%   (complex %.1f%% / assign %.1f%% / equals %.1f%%)\n",
		pct(failOpen), pct(complex), pct(assign), pct(equals))
	fmt.Fprintf(w, "  deny (grep-on-code)  : %.1f%%   observed denies in results: %d\n", pct(deny), a.DeniesObserved)
	fmt.Fprintf(w, "  ast-grep (sg) calls  : %d     grep/rg calls: %d\n", a.SgCalls, a.GrepCalls)
	fmt.Fprintf(w, "  lean-ctx ctx_* calls : %d     gitnexus calls: %d\n", a.CtxCalls, a.GitnexusCalls)
	fmt.Fprintf(w, "  native Read / Grep   : %d / %d\n", a.NativeReads, a.NativeGreps)
}

// cacheVerdict labels a cache hit rate against the 80% hygiene floor.
func cacheVerdict(rate float64) string {
	if rate >= 0.80 {
		return "healthy (≥ 80% floor)"
	}
	return "below the 80% floor — check cache hygiene (telemetry/gate.py, prompt-caching-playbook)"
}

// RenderCache is the `agentic cache` view: the same numbers as gain, led by the
// prompt-cache hit rate and the fresh/read/write split and input bill behind it.
// It drops the non-cache lines (output, subagent share, est. cost) so the stat
// the user asked for is front and centre.
func RenderCache(w io.Writer, r *Report, byModel bool) {
	if r.Sessions == 0 {
		fmt.Fprintln(w, "No sessions matched — run some work first, then `agentic cache`.")
		return
	}
	fmt.Fprintf(w, "agentic-cfg cache — prompt-cache economy over %d session(s)\n", r.Sessions)
	fmt.Fprintf(w, "  cache hit rate     : %.1f%%   (cache_read / total input) — %s\n", r.CacheHitRate*100, cacheVerdict(r.CacheHitRate))
	fmt.Fprintf(w, "  input (fresh)      : %s\n", fmtK(r.Input))
	fmt.Fprintf(w, "  cache read         : %s\n", fmtK(r.CacheRead))
	fmt.Fprintf(w, "  cache write        : %s\n", fmtK(r.CacheWrite))
	fmt.Fprintf(w, "  input bill (actual): $%.2f  (input + cache — what you actually paid)\n", r.InputCostReal)
	fmt.Fprintf(w, "  cache avoided      : $%.2f  (%.0f%% — vs re-sending uncached; the Claude platform cache, kept warm by cache hygiene)\n", r.InputCostSaved, r.InputSavedPct*100)
	if byModel && len(r.ByModel) > 0 {
		fmt.Fprintf(w, "\nby model (cache hit rate per tier):\n")
		unknown := false
		for _, m := range r.ByModel {
			name := m.Model
			if !m.Known {
				name += "*"
				unknown = true
			}
			fmt.Fprintf(w, "  %-26s hit %4.0f%%   in %8s\n", name, m.CacheHitRate*100, fmtK(m.TotalInput))
		}
		if unknown {
			fmt.Fprintln(w, "  * unknown model — billed at default (opus) rates in these estimates")
		}
	}
}

// Main is the `agentic gain` entry point.
func Main(args []string) int {
	fs := flag.NewFlagSet("gain", flag.ContinueOnError)
	root := fs.String("root", defaultRoot(), "transcript root (default: ~/.claude/projects)")
	last := fs.Int("last", 20, "number of most-recent sessions to include (0 = all)")
	project := fs.String("project", "", "filter by project/dir substring")
	asJSON := fs.Bool("json", false, "emit JSON instead of a table")
	byModel := fs.Bool("by-model", false, "append a per-model token breakdown")
	cacheView := fs.Bool("cache", false, "cache-focused readout (hit rate + token split + cost saved)")
	adoption := fs.Bool("adoption", false, "append an enforcement-coverage block: shell-guard wrap/deny/fail-open shares, ast-grep/lean-ctx/GitNexus adoption")
	gate := fs.Bool("gate", false, "regression gate: exit 1 if the cache hit rate is below --min-hit-rate")
	minRate := fs.Float64("min-hit-rate", 0.80, "cache-hit-rate floor for --gate")
	minTokens := fs.Int("min-tokens", 200000, "skip the gate (exit 0) below this many total input tokens (matches telemetry/gate.py)")
	fs.Usage = func() {
		fmt.Fprint(os.Stderr, "usage: agentic gain [--root DIR] [--last N] [--project SUBSTR] [--by-model] [--cache] [--adoption] [--json]\n"+
			"       agentic gain --gate [--min-hit-rate 0.80] [--min-tokens 200000]\n\n"+
			"Built-in performance readout from Claude Code transcripts: token volume,\n"+
			"prompt-cache hit rate, input cost avoided by caching, and subagent share.\n"+
			"--cache shows a cache-focused view (also reachable as `agentic cache`).\n"+
			"--adoption appends enforcement coverage: shell-guard wrap/deny/fail-open\n"+
			"shares and ast-grep/lean-ctx/GitNexus call counts.\n"+
			"--gate turns the cache hit rate into a pass/fail check for CI.\n")
	}
	if err := fs.Parse(args); err != nil {
		return 2
	}
	if _, err := os.Stat(*root); err != nil {
		fmt.Fprintf(os.Stderr, "agentic gain: transcript root not found: %s\n", *root)
		return 2
	}
	sessions, err := CollectOpts(*root, *project, *last, ParseOpts{Adoption: *adoption})
	if err != nil {
		fmt.Fprintf(os.Stderr, "agentic gain: %v\n", err)
		return 1
	}
	report := Aggregate(sessions)
	if *gate {
		verdict, code := Gate(&report, *minRate, *minTokens)
		fmt.Println(verdict)
		return code
	}
	switch {
	case *asJSON:
		Render(os.Stdout, &report, true, *byModel)
	case *cacheView:
		RenderCache(os.Stdout, &report, *byModel)
	default:
		Render(os.Stdout, &report, false, *byModel)
	}
	return 0
}

func defaultRoot() string {
	home, err := os.UserHomeDir()
	if err != nil {
		return ".claude/projects"
	}
	return filepath.Join(home, ".claude", "projects")
}
