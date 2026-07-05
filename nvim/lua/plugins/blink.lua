-- blink.cmp: completion with a Rust fuzzy matcher. Snippets use the builtin
-- vim.snippet engine, so no luasnip needed.
require('blink.cmp').setup({
  keymap = {
    preset = 'default', -- <C-y> accept, <C-n>/<C-p> select, <C-space> open
    -- Smart <Tab>: accept a visible Copilot suggestion first, otherwise fall
    -- through to blink's snippet jump, then a literal Tab.
    ['<Tab>'] = {
      function()
        local ok, sug = pcall(require, 'copilot.suggestion')
        if ok and sug.is_visible() then
          sug.accept()
          return true
        end
      end,
      'snippet_forward',
      'fallback',
    },
  },
  appearance = { nerd_font_variant = 'mono' },
  completion = {
    documentation = { auto_show = true, auto_show_delay_ms = 200 },
    -- Copilot owns the inline ghost text (see plugins/copilot.lua); keep
    -- blink's own ghost text off to avoid two overlapping inline previews.
    ghost_text = { enabled = false },
  },
  sources = {
    default = { 'lsp', 'path', 'snippets', 'buffer' },
  },
  -- [perf] Rust implementation (prebuilt binary shipped with the release tag).
  fuzzy = { implementation = 'prefer_rust_with_warning' },
  signature = { enabled = true },
})
