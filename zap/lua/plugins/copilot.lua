-- GitHub Copilot inline suggestions (ghost text). copilot.lua is the pure-Lua
-- client; it reuses the existing ~/.config/github-copilot login and spawns the
-- Copilot language server via `node` (present on PATH via mise).
require('copilot').setup({
  suggestion = {
    enabled = true,
    auto_trigger = true,            -- show a suggestion as you type
    hide_during_completion = true,  -- hide while the blink menu is open
    -- No Meta/Alt (macOS Option isn't Meta by default). <C-l> and <C-]> have no
    -- default insert-mode function and don't clash with blink. next/prev/word
    -- use kitty-protocol ctrl combos, which Ghostty sends.
    keymap = {
      accept = '<C-l>',       -- accept the whole suggestion
      accept_word = '<C-;>',  -- accept the next word only
      next = '<C-.>',         -- cycle to next suggestion
      prev = '<C-,>',         -- cycle to previous
      dismiss = '<C-]>',      -- dismiss the current suggestion
    },
  },
  panel = { enabled = false }, -- inline only, no panel window
})
