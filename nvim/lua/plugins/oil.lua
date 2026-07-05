-- oil.nvim: browse and edit the filesystem as a normal buffer. Rename/create/
-- delete/move files by editing text and :w to apply.
require('oil').setup({
  -- Open oil when you edit a directory (netrw is disabled in options.lua).
  default_file_explorer = true,
  columns = { 'icon' },
  view_options = {
    show_hidden = true, -- toggle in-buffer with `g.`
  },
  -- Confirm before applying filesystem changes.
  skip_confirm_for_simple_edits = false,
  keymaps = {
    ['q'] = 'actions.close',
    ['<Esc>'] = 'actions.close',
  },
})

-- `-` opens the parent directory of the current file (oil's signature mapping);
-- inside oil, `-` goes up, `<CR>` opens, `q`/`<Esc>` closes.
vim.keymap.set('n', '-', '<cmd>Oil<CR>', { desc = 'Open parent directory (oil)' })
-- Floating explorer rooted at the cwd.
vim.keymap.set('n', '<leader>o', function() require('oil').toggle_float() end, { desc = 'File explorer (oil float)' })
