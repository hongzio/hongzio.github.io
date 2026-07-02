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
