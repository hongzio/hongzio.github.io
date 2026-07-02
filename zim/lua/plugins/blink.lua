-- blink.cmp: completion with a Rust fuzzy matcher. Snippets use the builtin
-- vim.snippet engine, so no luasnip needed.
require('blink.cmp').setup({
  keymap = { preset = 'default' },   -- <C-y> accept, <C-n>/<C-p> select, <C-space> open
  appearance = { nerd_font_variant = 'mono' },
  completion = {
    documentation = { auto_show = true, auto_show_delay_ms = 200 },
    ghost_text = { enabled = true },
  },
  sources = {
    default = { 'lsp', 'path', 'snippets', 'buffer' },
  },
  -- [perf] Rust implementation (prebuilt binary shipped with the release tag).
  fuzzy = { implementation = 'prefer_rust_with_warning' },
  signature = { enabled = true },
})
