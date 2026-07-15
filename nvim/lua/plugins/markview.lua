-- markview.nvim: in-buffer markdown rendering (headings, code blocks, tables,
-- lists, LaTeX, ...). Driven by treesitter; parsers ensured in plugins.treesitter.
require('markview').setup({
  preview = {
    -- Render live while editing. Keep the cursor line rendered too (no hybrid
    -- unrendering) so the view stays fully rendered at all times.
    modes = { 'n', 'no', 'c' },
    hybrid_modes = {},
  },
})
