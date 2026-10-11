-- snacks.nvim: a curated, minimal set of quality-of-life modules. Picker is
-- intentionally left off (fzf-lua handles that).
require('snacks').setup({
  bigfile = { enabled = true },   -- [perf] disables heavy features on huge files
  quickfile = { enabled = true }, -- [perf] render the file before loading plugins
  notifier = { enabled = true },  -- replaces vim.notify with a nicer UI
  words = { enabled = true },     -- highlight/navigate LSP references under cursor
  indent = { enabled = true },    -- indent guides + scope
  input = { enabled = true },     -- better vim.ui.input
  statuscolumn = { enabled = true },
})

local map = vim.keymap.set
map('n', ']]', function() Snacks.words.jump(1) end, { desc = 'Next reference' })
map('n', '[[', function() Snacks.words.jump(-1) end, { desc = 'Prev reference' })
map('n', '<leader>n', function() Snacks.notifier.show_history() end, { desc = 'Notifications' })

-- Projects picker (recent git roots). Picks -> chdir + restore session if a
-- session backend exists. Lazy-loads the picker module (kept off in setup).
map('n', '<leader>fp', function() Snacks.picker.projects() end, { desc = 'Projects' })

-- Floating toggle terminal. Mapped in BOTH normal and terminal mode so the same
-- key opens it and closes it from inside (no need to leave terminal mode first).
-- Reuses the same instance, so it hides/restores. Inherits the shell env (mise).
--
-- Not on <leader>: a terminal-mode map that starts with <Space> holds every
-- space typed into the shell for 'timeoutlen'. <C-_> is the same key on a
-- terminal without the kitty keyboard protocol (Ctrl-/ arrives as 0x1F); the
-- cost is that a shell inside nvim loses Ctrl-_ (undo in zsh/readline).
local function toggle_terminal()
  Snacks.terminal.toggle(nil, { win = { position = 'float' } })
end
map({ 'n', 't' }, '<C-/>', toggle_terminal, { desc = 'Toggle terminal (float)' })
map({ 'n', 't' }, '<C-_>', toggle_terminal, { desc = 'Toggle terminal (float)' })
-- snacks already maps <Esc><Esc> inside the terminal to reach normal mode.
