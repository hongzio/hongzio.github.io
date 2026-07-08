-- General keymaps. Plugin-specific maps live next to their setup.
local map = vim.keymap.set

-- Clear search highlight.
map('n', '<Esc>', '<cmd>nohlsearch<CR>')

-- Window navigation. <C-j>/<C-k> are reassigned to function motions and <C-l>
-- to node-selection expand; use <C-w>h/j/k/l for splits.
map('n', '<C-h>', '<C-w>h')

-- Window ops under <leader>w (directional moves stay on <C-w>/<C-h> to avoid
-- duplication). <C-w> itself is untouched, so nothing is lost.
map('n', '<leader>w-', '<C-w>s', { desc = 'Split window (horizontal)' })
map('n', '<leader>w|', '<C-w>v', { desc = 'Split window (vertical)' })
map('n', '<leader>wc', '<C-w>c', { desc = 'Close window' })
map('n', '<leader>wq', '<C-w>q', { desc = 'Quit window' })
map('n', '<leader>wo', '<C-w>o', { desc = 'Only (close others)' })
map('n', '<leader>ww', '<C-w>w', { desc = 'Cycle to other window' })
map('n', '<leader>w=', '<C-w>=', { desc = 'Equalize window sizes' })
map('n', '<leader>wx', '<C-w>x', { desc = 'Exchange with next window' })
map('n', '<leader>wr', '<C-w>r', { desc = 'Rotate windows' })
map('n', '<leader>wT', '<C-w>T', { desc = 'Move window to new tab' })
map('n', '<leader>wH', '<C-w>H', { desc = 'Move window far left' })
map('n', '<leader>wJ', '<C-w>J', { desc = 'Move window far down' })
map('n', '<leader>wK', '<C-w>K', { desc = 'Move window far up' })
map('n', '<leader>wL', '<C-w>L', { desc = 'Move window far right' })

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
