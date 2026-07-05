-- flash.nvim: label-based motion. `s` + the letters at your target jumps there
-- in 2-3 keystrokes; `S` jumps to a treesitter node. f/t/F/T and `/` search are
-- enhanced with labels by default (no extra keymaps needed).
--
-- `s`/`S` replace the builtin substitute-char/line (use `cl`/`cc` instead);
-- mini.surround was moved to the `gs` prefix to free them (see surround.lua).
require('flash').setup()

local flash = require('flash')
vim.keymap.set({ 'n', 'x', 'o' }, 's', function() flash.jump() end, { desc = 'Flash jump' })
vim.keymap.set({ 'n', 'x', 'o' }, 'S', function() flash.treesitter() end, { desc = 'Flash treesitter' })
