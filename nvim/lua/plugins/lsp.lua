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

-- basedpyright (install: `uv tool install basedpyright`). Like gopls, a single
-- install serves every project and every Python version: it never runs the
-- project interpreter, it just statically reads each project's venv.
-- on_init locates the venv (mise-env's .mise/python/venv, or a plain .venv) and
-- points basedpyright at its interpreter so third-party imports resolve.
local venv_candidates = { '.mise/python/venv', '.venv' }

-- Return the interpreter path for the first venv that exists under `root`.
local function venv_python(root)
  if not root then return nil end
  for _, rel in ipairs(venv_candidates) do
    local py = root .. '/' .. rel .. '/bin/python'
    if vim.uv.fs_stat(py) then return py end
  end
end
vim.lsp.config('basedpyright', {
  cmd = { 'basedpyright-langserver', '--stdio' },
  filetypes = { 'python' },
  root_markers = {
    'pyproject.toml', 'setup.py', 'setup.cfg',
    'requirements.txt', 'pyrightconfig.json', '.git',
  },
  settings = {
    basedpyright = {
      analysis = {
        -- basedpyright defaults stricter than pyright; 'standard' keeps the
        -- diagnostics signal-to-noise close to upstream pyright.
        typeCheckingMode = 'standard',
        diagnosticMode = 'openFilesOnly', -- [perf] don't scan the whole tree
        useLibraryCodeForTypes = true,
      },
    },
  },
  -- Inject the interpreter after the client exists: mutate client.settings in
  -- place (reassigning it in before_init breaks the reference the server reads)
  -- and push it with didChangeConfiguration so the running server re-resolves.
  on_init = function(client)
    local root = client.root_dir or (client.config or {}).root_dir
    local py = venv_python(root)
    if not py then return end
    client.settings = vim.tbl_deep_extend('force', client.settings or {}, {
      python = { pythonPath = py },
    })
    client:notify('workspace/didChangeConfiguration', { settings = client.settings })
  end,
})

-- Enable the servers you have installed. Add more names here after declaring
-- their vim.lsp.config above.
vim.lsp.enable({ 'lua_ls', 'gopls', 'basedpyright' })

-- Extra keymaps on attach. Neovim 0.11 already provides defaults: K (hover),
-- grn (rename), <C-s> (signature help in insert). We override the navigation /
-- list actions with fzf-lua pickers (preview window with surrounding code), and
-- add grh/grs so hover and signature help live in the gr* family in normal mode
-- (K still works). Buffer-local maps take precedence over Neovim's gr* defaults.
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
    map('grh', vim.lsp.buf.hover, 'Hover')
    map('grs', vim.lsp.buf.signature_help, 'Signature help')
    map('<leader>f', function() vim.lsp.buf.format({ async = true }) end, 'Format buffer')

    -- [perf] Enable inlay hints if the server supports them.
    local client = vim.lsp.get_client_by_id(args.data.client_id)
    if client and client:supports_method('textDocument/inlayHint') then
      vim.lsp.inlay_hint.enable(true, { bufnr = buf })
    end
  end,
})
