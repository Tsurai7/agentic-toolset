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
	// opus m1: gross=2400*15=36000µ$, real=100*15+2000*1.5+300*18.75=10125µ$
	// haiku m2: gross=510*1=510µ$, real=10*1+500*0.1=60µ$
	wantGross := (36000.0 + 510.0) / 1e6
	wantReal := (10125.0 + 60.0) / 1e6
	if !approx(r.InputCostSaved, wantGross-wantReal, 1e-9) {
		t.Errorf("InputCostSaved = %v, want %v", r.InputCostSaved, wantGross-wantReal)
	}
	if !approx(r.InputSavedPct, (wantGross-wantReal)/wantGross, 1e-9) {
		t.Errorf("InputSavedPct = %v", r.InputSavedPct)
	}
	// Full estimated cost includes output tokens.
	wantCost := (10125.0 + 50*75 + 60.0 + 5*5) / 1e6
	if !approx(r.EstCostUSD, wantCost, 1e-9) {
		t.Errorf("EstCostUSD = %v, want %v", r.EstCostUSD, wantCost)
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
