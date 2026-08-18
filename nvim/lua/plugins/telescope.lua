-- telescope.nvim: picker framework. fzf-lua remains the daily driver and owns
-- the <leader>f* maps; telescope only carries the maps below.
require('telescope').setup({})

-- Note: while multicursor is active its layer claims <C-p> (delete cursor).
vim.keymap.set('n', '<C-p>', '<Cmd>Telescope keymaps<CR>', { desc = 'Telescope keymaps' })
