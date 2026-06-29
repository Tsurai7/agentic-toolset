// Package settings ports providers/shared/merge-settings.py. It merges the repo's
// own hook entries and permission allow-list into a provider settings.json while
// preserving user-added hooks, machine-local env, and every other key.
package settings

import (
	"encoding/json"
	"fmt"
	"os"
	"sort"
	"strings"

	"github.com/Tsurai7/agentic-cfg/internal/jsonorder"
)

// Merge merges the fragment at fragmentPath into the settings at outPath (read if
// present) and writes the result. Mirrors merge-settings.py.
func Merge(fragmentPath, outPath string) error {
	frag, err := jsonorder.ReadFile(fragmentPath)
	if err != nil {
		return fmt.Errorf("merge-settings: invalid JSON in %s: %w", fragmentPath, err)
	}
	out := jsonorder.New()
	if b, err := os.ReadFile(outPath); err == nil {
		if err := json.Unmarshal(b, out); err != nil {
			return fmt.Errorf("merge-settings: invalid JSON in %s: %w", outPath, err)
		}
	}
	mergeInto(out, frag)
	if os.Getenv("DRY_RUN") == "1" {
		data, err := jsonorder.Marshal(out)
		if err != nil {
			return err
		}
		fmt.Printf("[dry-run] would write %s:\n%s", outPath, data)
		return nil
	}
	return jsonorder.WriteFile(outPath, out)
}

// Unmerge removes the repo's managed hook groups and the fragment-owned permission
// allow entries from outPath, preserving user-added hooks, machine-local env, the
// deny list, and every other key. The inverse of Merge — used by `agentic eject`.
// No-op if outPath is absent. (Caveat: an allow entry the user added independently
// that also appears in the fragment is removed; this is documented behaviour.)
func Unmerge(fragmentPath, outPath string) error {
	frag, err := jsonorder.ReadFile(fragmentPath)
	if err != nil {
		return fmt.Errorf("unmerge-settings: invalid JSON in %s: %w", fragmentPath, err)
	}
	b, err := os.ReadFile(outPath)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return err
	}
	out := jsonorder.New()
	if err := json.Unmarshal(b, out); err != nil {
		return fmt.Errorf("unmerge-settings: invalid JSON in %s: %w", outPath, err)
	}
	unmergeHooks(out, frag)
	unmergePermissions(out, frag)
	return jsonorder.WriteFile(outPath, out)
}

func unmergeHooks(out, frag *jsonorder.Map) {
	outHooksRaw, ok := out.GetRaw("hooks")
	if !ok {
		return
	}
	fragHooksRaw, ok := frag.GetRaw("hooks")
	if !ok {
		return
	}
	outHooks := jsonorder.New()
	_ = json.Unmarshal(outHooksRaw, outHooks)
	fragHooks := jsonorder.New()
	_ = json.Unmarshal(fragHooksRaw, fragHooks)
	managed := managedCommands(fragHooks)
	for _, event := range fragHooks.Keys() {
		r, ok := outHooks.GetRaw(event)
		if !ok {
			continue
		}
		var groups []json.RawMessage
		_ = json.Unmarshal(r, &groups)
		var kept []json.RawMessage
		for _, g := range groups {
			if !isManagedGroup(g, managed) {
				kept = append(kept, g)
			}
		}
		if len(kept) == 0 {
			outHooks.Delete(event) // event held only managed groups
		} else {
			cb, _ := json.Marshal(kept)
			outHooks.SetRaw(event, cb)
		}
	}
	if len(outHooks.Keys()) == 0 {
		out.Delete("hooks")
	} else {
		hb, _ := json.Marshal(outHooks)
		out.SetRaw("hooks", hb)
	}
}

func unmergePermissions(out, frag *jsonorder.Map) {
	rawPerms, ok := out.GetRaw("permissions")
	if !ok {
		return
	}
	perms := jsonorder.New()
	_ = json.Unmarshal(rawPerms, perms)
	managedAllow := map[string]bool{}
	if r, ok := frag.GetRaw("permissions"); ok {
		fp := jsonorder.New()
		_ = json.Unmarshal(r, fp)
		for _, a := range permAllow(fp) {
			managedAllow[a] = true
		}
	}
	kept := []string{}
	for _, a := range permAllow(perms) {
		if !managedAllow[a] {
			kept = append(kept, a)
		}
	}
	sort.Strings(kept)
	ab, _ := json.Marshal(kept)
	perms.SetRaw("allow", ab)
	pb, _ := json.Marshal(perms)
	out.SetRaw("permissions", pb)
}

func mergeInto(out, frag *jsonorder.Map) {
	// $schema: only carry over a non-null fragment value, and only if absent.
	if raw, ok := frag.GetRaw("$schema"); ok && strings.TrimSpace(string(raw)) != "null" {
		if !out.Has("$schema") {
			out.SetRaw("$schema", raw)
		}
	}
	// hooks: deep-merge by event, preserving user-added hooks.
	if fragHooks, ok := frag.GetRaw("hooks"); ok {
		existing, _ := out.GetRaw("hooks")
		out.SetRaw("hooks", mergeHooks(existing, fragHooks))
	}
	// permissions: union allow, keep existing deny and any other keys.
	mergePermissions(out, frag)
}

// mergeHooks replaces the repo's own hook groups and preserves every user-added
// hook. Events the fragment does not mention are left untouched; within an event,
// only fully-managed groups are dropped before the fragment's groups are appended.
func mergeHooks(existingRaw, fragRaw json.RawMessage) json.RawMessage {
	frag := jsonorder.New()
	_ = json.Unmarshal(fragRaw, frag)
	existing := jsonorder.New()
	if len(existingRaw) > 0 {
		_ = json.Unmarshal(existingRaw, existing)
	}
	managed := managedCommands(frag)
	result := existing.Clone() // preserve user events and their order
	for _, event := range frag.Keys() {
		var fragGroups []json.RawMessage
		if r, ok := frag.GetRaw(event); ok {
			_ = json.Unmarshal(r, &fragGroups)
		}
		var kept []json.RawMessage
		if r, ok := existing.GetRaw(event); ok {
			var existingGroups []json.RawMessage
			_ = json.Unmarshal(r, &existingGroups)
			for _, g := range existingGroups {
				if !isManagedGroup(g, managed) {
					kept = append(kept, g)
				}
			}
		}
		kept = append(kept, fragGroups...)
		cb, _ := json.Marshal(kept)
		result.SetRaw(event, cb)
	}
	rb, _ := json.Marshal(result)
	return rb
}

func managedCommands(frag *jsonorder.Map) map[string]bool {
	set := map[string]bool{}
	for _, event := range frag.Keys() {
		var groups []json.RawMessage
		if r, ok := frag.GetRaw(event); ok {
			_ = json.Unmarshal(r, &groups)
		}
		for _, g := range groups {
			for _, c := range groupCommands(g) {
				if c != "" {
					set[c] = true
				}
			}
		}
	}
	return set
}

func groupCommands(g json.RawMessage) []string {
	var grp struct {
		Hooks []struct {
			Command string `json:"command"`
		} `json:"hooks"`
	}
	_ = json.Unmarshal(g, &grp)
	out := make([]string, 0, len(grp.Hooks))
	for _, h := range grp.Hooks {
		out = append(out, h.Command)
	}
	return out
}

// isManagedGroup is true only if every command in the group is one the repo owns,
// so it is safe to replace. A group containing any user command is left untouched.
func isManagedGroup(g json.RawMessage, managed map[string]bool) bool {
	cmds := groupCommands(g)
	if len(cmds) == 0 {
		return false
	}
	for _, c := range cmds {
		switch {
		case managed[c]:
		case strings.Contains(c, "/providers/claude/hooks/"):
		case strings.HasPrefix(c, "lean-ctx hook "):
		default:
			return false
		}
	}
	return true
}

func mergePermissions(out, frag *jsonorder.Map) {
	perms := jsonorder.New()
	if r, ok := out.GetRaw("permissions"); ok {
		_ = json.Unmarshal(r, perms)
	}
	allow := map[string]bool{}
	for _, a := range permAllow(perms) {
		allow[a] = true
	}
	if r, ok := frag.GetRaw("permissions"); ok {
		fp := jsonorder.New()
		_ = json.Unmarshal(r, fp)
		for _, a := range permAllow(fp) {
			allow[a] = true
		}
	}
	list := make([]string, 0, len(allow))
	for a := range allow {
		list = append(list, a)
	}
	sort.Strings(list)
	ab, _ := json.Marshal(list)
	perms.SetRaw("allow", ab)
	if !perms.Has("deny") {
		perms.SetRaw("deny", json.RawMessage("[]"))
	}
	pb, _ := json.Marshal(perms)
	out.SetRaw("permissions", pb)
}

func permAllow(m *jsonorder.Map) []string {
	if r, ok := m.GetRaw("allow"); ok {
		var a []string
		_ = json.Unmarshal(r, &a)
		return a
	}
	return nil
}
