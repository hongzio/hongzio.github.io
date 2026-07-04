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
map({ 'n', 't' }, '<leader>tt', function()
  Snacks.terminal.toggle(nil, { win = { position = 'float' } })
end, { desc = 'Toggle terminal (float)' })
-- snacks already maps <Esc><Esc> inside the terminal to reach normal mode.
