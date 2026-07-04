-- Native LSP via vim.lsp.config / vim.lsp.enable (Neovim 0.11+). No
-- nvim-lspconfig: we declare cmd/filetypes/root_markers ourselves.

-- Advertise blink's completion capabilities to every server.
vim.lsp.config('*', {
  capabilities = require('blink.cmp').get_lsp_capabilities(),
})

-- lua-language-server (install: brew install lua-language-server).
vim.lsp.config('lua_ls', {
  cmd = { 'lua-language-server' },
  filetypes = { 'lua' },
  root_markers = { '.luarc.json', '.luarc.jsonc', 'stylua.toml', '.git' },
  settings = {
    Lua = {
      runtime = { version = 'LuaJIT' },
      workspace = { checkThirdParty = false },
      telemetry = { enable = false },
      diagnostics = { globals = { 'vim' } },
    },
  },
})

-- gopls (install: mise use -g "go:golang.org/x/tools/gopls@latest").
-- A single gopls serves every project; it shells out to the `go` on PATH, so
-- per-project Go versions are resolved by GOTOOLCHAIN=auto / mise, not here.
vim.lsp.config('gopls', {
  cmd = { 'gopls' },
  filetypes = { 'go', 'gomod', 'gowork', 'gotmpl' },
  root_markers = { 'go.work', 'go.mod', '.git' },
  settings = {
    gopls = {
      gofumpt = true,
      staticcheck = true,
      analyses = { unusedparams = true, nilness = true, unusedwrite = true },
      hints = {
        assignVariableTypes = true,
        compositeLiteralFields = true,
        constantValues = true,
        functionTypeParameters = true,
        parameterNames = true,
        rangeVariableTypes = true,
      },
    },
  },
})

-- Enable the servers you have installed. Add more names here after declaring
-- their vim.lsp.config above.
vim.lsp.enable({ 'lua_ls', 'gopls' })

-- Extra keymaps on attach. Neovim 0.11 already provides defaults: K (hover),
-- grn (rename), <C-s> (signature help in insert). We override the navigation /
-- list actions with fzf-lua pickers (preview window with surrounding code).
-- Buffer-local maps take precedence over Neovim's global gr* defaults.
vim.api.nvim_create_autocmd('LspAttach', {
  callback = function(args)
    local buf = args.buf
    local fzf = require('fzf-lua')
    local map = function(keys, fn, desc)
      vim.keymap.set('n', keys, fn, { buffer = buf, desc = desc })
    end
    map('gd', fzf.lsp_definitions, 'Definitions')
    map('gD', fzf.lsp_declarations, 'Declarations')
    map('grr', fzf.lsp_references, 'References')
    map('gri', fzf.lsp_implementations, 'Implementations')
    map('grt', fzf.lsp_typedefs, 'Type definitions')
    map('gra', fzf.lsp_code_actions, 'Code actions')
    map('<leader>f', function() vim.lsp.buf.format({ async = true }) end, 'Format buffer')

    -- [perf] Enable inlay hints if the server supports them.
    local client = vim.lsp.get_client_by_id(args.data.client_id)
    if client and client:supports_method('textDocument/inlayHint') then
      vim.lsp.inlay_hint.enable(true, { bufnr = buf })
    end
  end,
})
