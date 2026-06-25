// Package installtest holds integration tests that drive the real installer
// scripts against a throwaway fixture $HOME, verifying the toolset's install path
// end to end (CLAUDE.md @import, settings hook merge, generated config) with user
// content preserved. These complement the per-package unit tests.
package installtest
