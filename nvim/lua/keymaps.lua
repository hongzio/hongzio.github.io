-- General keymaps. Plugin-specific maps live next to their setup.
local map = vim.keymap.set

-- Clear search highlight.
map('n', '<Esc>', '<cmd>nohlsearch<CR>')

-- Window navigation. <C-j>/<C-k> are reassigned to function motions and <C-l>
-- to node-selection expand; use <C-w>h/j/k/l for splits.
map('n', '<C-h>', '<C-w>h')

-- Keep cursor centered on jumps.
map('n', '<C-d>', '<C-d>zz')
map('n', '<C-u>', '<C-u>zz')
map('n', 'n', 'nzzzv')
map('n', 'N', 'Nzzzv')

-- Move selected lines.
map('v', 'J', ":m '>+1<CR>gv=gv")
map('v', 'K', ":m '<-2<CR>gv=gv")

-- Diagnostics.
map('n', '<leader>e', vim.diagnostic.open_float, { desc = 'Line diagnostics' })
map('n', '<leader>q', vim.diagnostic.setloclist, { desc = 'Diagnostics to loclist' })
