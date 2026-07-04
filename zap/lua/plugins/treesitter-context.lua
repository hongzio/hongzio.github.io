-- Sticky context: pins the enclosing function/block to the top of the window
-- so you keep the signature in view while scrolling a long body.
require('treesitter-context').setup({
  max_lines = 3,        -- cap the header height; keeps it out of the way
  multiline_threshold = 1, -- collapse multiline context lines to one
  mode = 'cursor',      -- track the cursor's scope, not just the top line
  separator = nil,      -- no underline separator (minimal)
})

-- Toggle, matching the <leader>t* toggle convention (tt terminal, tb blame).
vim.keymap.set('n', '<leader>tc', function()
  require('treesitter-context').toggle()
end, { desc = 'Toggle treesitter context' })
