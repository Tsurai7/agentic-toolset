package gain

import (
	"math"
	"strings"
	"testing"
)

// A transcript exercising: a main assistant turn, a DUPLICATE content-block
// record with the same message.id (must be counted once), a subagent sidechain
// turn, a non-assistant record, and a malformed line (both skipped).
const sample = `{"type":"user","message":{"role":"user"}}
{"type":"assistant","isSidechain":false,"sessionId":"sess-1","cwd":"/x/agentic-cfg","gitBranch":"master","message":{"id":"m1","model":"claude-opus-4-8","usage":{"input_tokens":100,"output_tokens":50,"cache_read_input_tokens":2000,"cache_creation_input_tokens":300,"cache_creation":{"ephemeral_5m_input_tokens":300,"ephemeral_1h_input_tokens":0}}}}
{"type":"assistant","isSidechain":false,"message":{"id":"m1","model":"claude-opus-4-8","usage":{"input_tokens":100,"output_tokens":50,"cache_read_input_tokens":2000,"cache_creation_input_tokens":300}}}
{not valid json
{"type":"assistant","isSidechain":true,"message":{"id":"m2","model":"claude-haiku-4-5","usage":{"input_tokens":10,"output_tokens":5,"cache_read_input_tokens":500,"cache_creation_input_tokens":0}}}`

func approx(a, b, eps float64) bool { return math.Abs(a-b) < eps }

// adoptionSample exercises every AdoptionStats tally: an rtk-wrapped Bash
// (already-wrapped), a heredoc Bash (fail-open complex), a grep-on-code Bash
// (deny + a grep/rg call), an `sg run` Bash (wrapped + an ast-grep call), a
// lean-ctx ctx_read tool_use, a native Read tool_use, and a user tool_result
// carrying the ast-grep deny reason text (an observed deny).
const adoptionSample = `{"type":"assistant","isSidechain":false,"sessionId":"sess-adopt","cwd":"/x/agentic-cfg","gitBranch":"master","message":{"id":"a1","model":"claude-sonnet-5","usage":{"input_tokens":100,"output_tokens":50,"cache_read_input_tokens":0,"cache_creation_input_tokens":0},"content":[{"type":"tool_use","name":"Bash","input":{"command":"rtk npm test"}}]}}
{"type":"assistant","message":{"id":"a2","model":"claude-sonnet-5","content":[{"type":"tool_use","name":"Bash","input":{"command":"cat <<EOF\nhi\nEOF"}}]}}
{"type":"assistant","message":{"id":"a3","model":"claude-sonnet-5","content":[{"type":"tool_use","name":"Bash","input":{"command":"grep TODO main.go"}}]}}
{"type":"assistant","message":{"id":"a4","model":"claude-sonnet-5","content":[{"type":"tool_use","name":"Bash","input":{"command":"sg run -p 'foo' -l go"}}]}}
{"type":"assistant","message":{"id":"a5","model":"claude-sonnet-5","content":[{"type":"tool_use","name":"mcp__lean-ctx__ctx_read","input":{"path":"x.go"}}]}}
{"type":"assistant","message":{"id":"a6","model":"claude-sonnet-5","content":[{"type":"tool_use","name":"Read","input":{"file_path":"x.go"}}]}}
{"type":"user","message":{"content":[{"type":"tool_result","content":"Use ast-grep for structural code search: sg -p '<pattern>' -l <lang>."}]}}`

func TestAdoptionStatsExactTallies(t *testing.T) {
	s, err := ParseLinesOpts(strings.NewReader(adoptionSample), ParseOpts{Adoption: true})
	if err != nil {
		t.Fatalf("ParseLinesOpts: %v", err)
	}
	if s == nil {
		t.Fatal("expected a session, got nil")
	}
	if s.Adoption == nil {
		t.Fatal("expected Adoption to be collected")
	}
	a := s.Adoption
	if a.BashTotal != 4 {
		t.Errorf("BashTotal = %d, want 4", a.BashTotal)
	}
	wantByDecision := map[string]int{
		"already-wrapped":   1,
		"failopen-complex":  1,
		"deny-grep-on-code": 1,
		"wrap":              1,
	}
	if len(a.ByDecision) != len(wantByDecision) {
		t.Errorf("ByDecision = %+v, want %+v", a.ByDecision, wantByDecision)
	}
	for k, v := range wantByDecision {
		if a.ByDecision[k] != v {
			t.Errorf("ByDecision[%q] = %d, want %d", k, a.ByDecision[k], v)
		}
	}
	if a.DeniesObserved != 1 {
		t.Errorf("DeniesObserved = %d, want 1", a.DeniesObserved)
	}
	if a.SgCalls != 1 {
		t.Errorf("SgCalls = %d, want 1", a.SgCalls)
	}
	if a.GrepCalls != 1 {
		t.Errorf("GrepCalls = %d, want 1", a.GrepCalls)
	}
	if a.CtxCalls != 1 {
		t.Errorf("CtxCalls = %d, want 1", a.CtxCalls)
	}
	if a.GitnexusCalls != 0 {
		t.Errorf("GitnexusCalls = %d, want 0", a.GitnexusCalls)
	}
	if a.NativeReads != 1 {
		t.Errorf("NativeReads = %d, want 1", a.NativeReads)
	}
	if a.NativeGreps != 0 {
		t.Errorf("NativeGreps = %d, want 0", a.NativeGreps)
	}
}

func TestAdoptionOffByDefault(t *testing.T) {
	s, err := ParseLines(strings.NewReader(adoptionSample))
	if err != nil {
		t.Fatalf("ParseLines: %v", err)
	}
	if s == nil {
		t.Fatal("expected a session, got nil")
	}
	if s.Adoption != nil {
		t.Errorf("Adoption = %+v, want nil when ParseOpts.Adoption is false", s.Adoption)
	}
}

func TestParseLinesDedupAndBuckets(t *testing.T) {
	s, err := ParseLines(strings.NewReader(sample))
	if err != nil {
		t.Fatalf("ParseLines: %v", err)
	}
	if s == nil {
		t.Fatal("expected a session, got nil")
	}
	// m1 appears twice (same id) but must be counted once; m2 once.
	if s.AssistantTurns != 2 {
		t.Errorf("AssistantTurns = %d, want 2 (dedup by message.id)", s.AssistantTurns)
	}
	if s.ID != "sess-1" || s.Project != "agentic-cfg" || s.Branch != "master" {
		t.Errorf("meta = %q/%q/%q, want sess-1/agentic-cfg/master", s.ID, s.Project, s.Branch)
	}
	if s.Main != (Bucket{Input: 100, Output: 50, CacheRead: 2000, CacheWrite: 300}) {
		t.Errorf("main bucket = %+v", s.Main)
	}
	if s.Sub != (Bucket{Input: 10, Output: 5, CacheRead: 500, CacheWrite: 0}) {
		t.Errorf("sub bucket = %+v", s.Sub)
	}
	if s.TotalInput() != 2910 { // 2400 main + 510 sub
		t.Errorf("TotalInput = %d, want 2910", s.TotalInput())
	}
	if !approx(s.CacheHitRate(), 2500.0/2910.0, 1e-9) {
		t.Errorf("CacheHitRate = %v, want %v", s.CacheHitRate(), 2500.0/2910.0)
	}
}

func TestAggregateGain(t *testing.T) {
	s, _ := ParseLines(strings.NewReader(sample))
	r := Aggregate([]*Session{s})

	if r.Sessions != 1 || r.Input != 110 || r.CacheRead != 2500 || r.CacheWrite != 300 || r.Output != 55 {
		t.Errorf("aggregate tallies = %+v", r)
	}
	if r.TotalInput != 2910 || r.SubInput != 510 {
		t.Errorf("TotalInput=%d SubInput=%d", r.TotalInput, r.SubInput)
	}
	if !approx(r.CacheHitRate, 2500.0/2910.0, 1e-9) {
		t.Errorf("CacheHitRate = %v", r.CacheHitRate)
	}
	if !approx(r.SubagentShare, 510.0/2910.0, 1e-9) {
		t.Errorf("SubagentShare = %v", r.SubagentShare)
	}
	// Input cost saved: gross (all input billed fresh) minus real (cache-discounted).
	// opus m1: gross=2400*5=12000µ$, real=100*5+2000*0.5+300*6.25=3375µ$
	// haiku m2: gross=510*1=510µ$, real=10*1+500*0.1=60µ$
	wantGross := (12000.0 + 510.0) / 1e6
	wantReal := (3375.0 + 60.0) / 1e6
	if !approx(r.InputCostReal, wantReal, 1e-9) { // the actual input bill must be exposed, not just the counterfactual
		t.Errorf("InputCostReal = %v, want %v", r.InputCostReal, wantReal)
	}
	if !approx(r.InputCostSaved, wantGross-wantReal, 1e-9) {
		t.Errorf("InputCostSaved = %v, want %v", r.InputCostSaved, wantGross-wantReal)
	}
	if !approx(r.InputSavedPct, (wantGross-wantReal)/wantGross, 1e-9) {
		t.Errorf("InputSavedPct = %v", r.InputSavedPct)
	}
	// Full estimated cost includes output tokens.
	wantCost := (3375.0 + 50*25 + 60.0 + 5*5) / 1e6
	if !approx(r.EstCostUSD, wantCost, 1e-9) {
		t.Errorf("EstCostUSD = %v, want %v", r.EstCostUSD, wantCost)
	}
}

func TestGate(t *testing.T) {
	cases := []struct {
		name     string
		r        Report
		minRate  float64
		minToks  int
		wantCode int
		wantHas  string
	}{
		{"pass above floor", Report{TotalInput: 100000, CacheRead: 95000, CacheHitRate: 0.95}, 0.80, 50000, 0, "PASS"},
		{"fail below floor", Report{TotalInput: 100000, CacheRead: 50000, CacheHitRate: 0.50}, 0.80, 50000, 1, "FAIL"},
		{"boundary inclusive", Report{TotalInput: 100000, CacheRead: 80000, CacheHitRate: 0.80}, 0.80, 50000, 0, "PASS"},
		{"skip small sample", Report{TotalInput: 1000, CacheRead: 0, CacheHitRate: 0.0}, 0.80, 50000, 0, "SKIP"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			verdict, code := Gate(&c.r, c.minRate, c.minToks)
			if code != c.wantCode {
				t.Errorf("code = %d, want %d (%q)", code, c.wantCode, verdict)
			}
			if !strings.Contains(verdict, c.wantHas) {
				t.Errorf("verdict = %q, want to contain %q", verdict, c.wantHas)
			}
		})
	}
}

func TestPerModelBreakdown(t *testing.T) {
	s, _ := ParseLines(strings.NewReader(sample))
	r := Aggregate([]*Session{s})
	if len(r.ByModel) != 2 {
		t.Fatalf("ByModel len = %d, want 2 (%+v)", len(r.ByModel), r.ByModel)
	}
	// Sorted by total input desc: opus main (2400) then haiku sidechain (510).
	if r.ByModel[0].Model != "claude-opus-4-8" || r.ByModel[0].TotalInput != 2400 {
		t.Errorf("ByModel[0] = %+v, want opus/2400", r.ByModel[0])
	}
	if r.ByModel[1].Model != "claude-haiku-4-5" || r.ByModel[1].TotalInput != 510 {
		t.Errorf("ByModel[1] = %+v, want haiku/510", r.ByModel[1])
	}
	if !approx(r.ByModel[0].InputShare, 2400.0/2910.0, 1e-9) {
		t.Errorf("opus input share = %v", r.ByModel[0].InputShare)
	}
	if !approx(r.ByModel[1].CacheHitRate, 500.0/510.0, 1e-9) {
		t.Errorf("haiku hit rate = %v", r.ByModel[1].CacheHitRate)
	}
}

func TestNoUsableTurns(t *testing.T) {
	for _, in := range []string{"", "{bad\n{\"type\":\"user\"}\n", `{"type":"assistant","message":{"id":"x"}}`} {
		s, err := ParseLines(strings.NewReader(in))
		if err != nil {
			t.Fatalf("ParseLines(%q): %v", in, err)
		}
		if s != nil {
			t.Errorf("ParseLines(%q) = %+v, want nil (no usage-bearing turns)", in, s)
		}
	}
}

// The cache-focused view leads with the hit rate, keeps the token split + cost
// saved, and drops the non-cache lines (output, subagent share, est. cost). Its
// empty-state message must name the `cache` command, not `gain`.
func TestRenderCache(t *testing.T) {
	r := Report{
		Sessions: 3, Input: 100, CacheRead: 9000, CacheWrite: 200, Output: 500,
		CacheHitRate: 0.981, InputCostReal: 7.00, InputCostSaved: 42.50, InputSavedPct: 0.87,
		SubagentShare: 0.2, EstCostUSD: 12.0,
	}
	var b strings.Builder
	RenderCache(&b, &r, false)
	out := b.String()
	// Honest framing: the actual bill is shown, and the counterfactual is labeled
	// "cache avoided" (vs the old "cost saved"), not attributed to the config.
	for _, want := range []string{"cache hit rate", "98.1%", "healthy", "input bill (actual)", "$7.00", "cache avoided", "$42.50"} {
		if !strings.Contains(out, want) {
			t.Errorf("RenderCache output missing %q:\n%s", want, out)
		}
	}
	for _, drop := range []string{"subagent share", "est. cost"} {
		if strings.Contains(out, drop) {
			t.Errorf("RenderCache should drop %q from the cache view:\n%s", drop, out)
		}
	}
	var empty strings.Builder
	RenderCache(&empty, &Report{Sessions: 0}, false)
	if !strings.Contains(empty.String(), "agentic cache") {
		t.Errorf("empty-state message should name `agentic cache`: %q", empty.String())
	}
}

// A cache-write-heavy session with no reuse must show NEGATIVE savings — writing
// cache costs more than fresh input (5m write ~1.25x), so the metric is honest
// rather than always-positive.
func TestNegativeSavingsWhenCacheNeverReused(t *testing.T) {
	writeOnly := `{"type":"assistant","message":{"id":"w","model":"claude-opus-4-8","usage":{"input_tokens":10,"output_tokens":1,"cache_read_input_tokens":0,"cache_creation_input_tokens":100000,"cache_creation":{"ephemeral_5m_input_tokens":100000}}}}`
	s, _ := ParseLines(strings.NewReader(writeOnly))
	r := Aggregate([]*Session{s})
	if r.InputCostSaved >= 0 {
		t.Errorf("InputCostSaved = %v, want negative for write-only/no-reuse", r.InputCostSaved)
	}
}

func TestRatesFor(t *testing.T) {
	cases := []struct {
		model string
		want  rate
	}{
		{"claude-fable-5", rate{10.0, 1.0, 12.5, 20.0, 50.0}},
		{"claude-mythos-5", rate{10.0, 1.0, 12.5, 20.0, 50.0}},
		{"claude-opus-4-8", rate{5.0, 0.5, 6.25, 10.0, 25.0}},
		{"claude-sonnet-5", rate{3.0, 0.3, 3.75, 6.0, 15.0}},
		{"claude-haiku-4-5", rate{1.0, 0.1, 1.25, 2.0, 5.0}},
		{"totally-unknown-model", rate{5.0, 0.5, 6.25, 10.0, 25.0}}, // falls back to opus
	}
	for _, c := range cases {
		if got := ratesFor(c.model); got != c.want {
			t.Errorf("ratesFor(%q) = %+v, want %+v", c.model, got, c.want)
		}
	}
}

func TestKnownModel(t *testing.T) {
	for _, m := range []string{"claude-fable-5", "claude-mythos-5", "claude-opus-4-8", "claude-sonnet-5", "claude-haiku-4-5"} {
		if !knownModel(m) {
			t.Errorf("knownModel(%q) = false, want true", m)
		}
	}
	if knownModel("totally-unknown-model") {
		t.Error("knownModel(\"totally-unknown-model\") = true, want false")
	}
}
