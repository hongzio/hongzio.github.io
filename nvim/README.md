# nvim

Minimal, high-performance Neovim config (Neovim 0.12+). Leans on builtins
(`vim.pack`, native LSP, treesitter) and a small set of fast, pure-Lua plugins.

The default config: lives in `~/.config/nvim` and runs with plain `nvim` — no
`NVIM_APPNAME` needed.

## Stack

| Concern         | Choice                                            |
|-----------------|---------------------------------------------------|
| Plugin manager  | builtin `vim.pack`                                |
| LSP             | builtin `vim.lsp.config` / `enable` (no lspconfig) |
| Completion      | `blink.cmp` (Rust fuzzy matcher)                  |
| AI suggestions  | `copilot.lua` (inline ghost text)                 |
| Fuzzy finder    | `fzf-lua` (`max-perf` profile)                    |
| Syntax          | `nvim-treesitter` (`main`) + `-textobjects` + `-context` |
| Colorscheme     | `monokai-pro.nvim` (`pro` filter)                 |
| Git             | `gitsigns.nvim`                                   |
| File explorer   | `oil.nvim`                                        |
| Multicursor     | `multicursor.nvim`                                |
| Surround        | `mini.surround` (`sa` / `sd` / `sr`)              |
| Increment       | `dial.nvim` (`<C-a>` / `<C-x>`, per-filetype)     |
| QoL             | `snacks.nvim`                                     |
| Icons / statusline | `mini.icons` / `mini.statusline`               |

## Requirements

- Neovim 0.12+
- A C compiler (`cc`/`gcc`) — for building treesitter parsers
- `tree-sitter` CLI — the treesitter `main` branch compiles parsers with it
  (Homebrew's `tree-sitter` formula is the library only; the CLI is separate)

```sh
brew install tree-sitter-cli
```

## First launch

Plugins clone automatically on the first start. Treesitter parsers install
themselves the first time you open a file of a given language (see
`lua/plugins/treesitter.lua`).

### Language servers

Native LSP declares servers directly (no `nvim-lspconfig`). Configured out of
the box:

- `lua_ls` — `brew install lua-language-server`
- `gopls` — `mise use -g "go:golang.org/x/tools/gopls@latest"` (a single gopls
  serves every project; per-project Go versions resolve via `GOTOOLCHAIN=auto`
  / mise)
- `basedpyright` — `uv tool install basedpyright` (a single install serves every
  project and Python version; `on_init` points it at the project venv
  — `.mise/python/venv` or a plain `.venv` — so its packages resolve)

Add a server: declare `vim.lsp.config('<name>', {...})` and add its name to
`vim.lsp.enable({...})` in `lua/plugins/lsp.lua`.

## Keybindings

Leader is `<Space>`.

### Movement & editing

| Key | Action |
|-----|--------|
| `<C-h>` | Window left (`<C-w>h/j/k/l` for all directions) |
| `<C-d>` / `<C-u>` | Half-page scroll (centered) |
| `]f` / `[f`, `<C-j>` / `<C-k>` | Next / prev **named** function (skips anonymous) |
| `]F` / `[F` | Next / prev function end |
| `<C-l>` | Select treesitter node; repeat to expand to parent |
| `<C-h>` (visual) | Shrink node selection |

### LSP (buffer-local, fzf-lua pickers with preview)

| Key | Action |
|-----|--------|
| `gd` / `gD` | Definitions / declarations |
| `grr` / `gri` / `grt` | References / implementations / type definitions |
| `gra` / `grn` | Code actions / rename |
| `K` / `gO` | Hover / document symbols |
| `<leader>f` | Format buffer |

### Find (fzf-lua)

| Key | Action |
|-----|--------|
| `<leader>ff` / `<leader><space>` | Files |
| `<leader>fg` | Live grep |
| `<leader>fb` / `<leader>fo` | Buffers / recent files |
| `<leader>fp` | Projects (recent git roots, snacks) |
| `<leader>fr` | Resume last picker |
| `<leader>fh` / `<leader>fd` | Help / diagnostics |
| `<leader>fs` / `<leader>fS` | Document symbols / workspace symbols (live) |
| `<leader>/` | Search in current buffer |

### Git (gitsigns)

| Key | Action |
|-----|--------|
| `]h` / `[h` | Next / prev hunk (staged + unstaged) |
| `<leader>hp` / `<leader>hi` | Preview hunk (popup / inline) |
| `<leader>hr` / `<leader>hR` | Reset hunk / buffer |
| `<leader>hs` / `<leader>hS` / `<leader>hu` | Stage hunk / buffer / undo stage |
| `<leader>hb` / `<leader>tb` | Blame line / toggle inline blame |
| `<leader>hd` / `<leader>hD` | Diff vs index / last commit |
| `<leader>fc` / `<leader>fC` | File history / project commits (fzf) |
| `ih` | Hunk text object (`dih`, `vih`) |

### Multicursor

| Key | Action |
|-----|--------|
| `<C-Up>` / `<C-Down>` | Add cursor above / below |
| `<C-n>` | Add cursor at next match (Cmd+D) |
| `<leader>mp` / `<leader>ms` | Add prev match / skip match |
| `<leader>mA` / `<leader>mr` | All matches / restore cursors |
| (while active) `<Esc>` | Disable, then clear cursors |
| (while active) `<C-p>` / `<leader>x` | Delete current cursor |

### Increment / decrement (dial)

Rule group is chosen by filetype (numbers, hex, dates, booleans, logical /
comparison operators, weekdays, months, semver, ...).

| Key | Action |
|-----|--------|
| `<C-a>` / `<C-x>` | Increment / decrement under cursor (normal + visual) |
| `g<C-a>` / `g<C-x>` | Visual: ramp values per line (1, 2, 3, ...) |

### File explorer (oil)

| Key | Action |
|-----|--------|
| `-` | Open parent directory |
| `<leader>o` | Floating explorer (cwd) |

In an oil buffer: edit lines then `:w` to rename/create/delete/move files;
`g?` shows all mappings.

### Copilot (insert mode, inline ghost text)

| Key | Action |
|-----|--------|
| `<Tab>` | Accept suggestion (else falls back to snippet jump / indent) |
| `<C-l>` | Accept suggestion (alternative) |
| `<C-;>` | Accept next word |
| `<C-.>` / `<C-,>` | Next / previous suggestion |
| `<C-]>` | Dismiss |

Auth is reused from `~/.config/github-copilot`; run `:Copilot auth` once if
needed and `:Copilot status` to check. Requires `node` on `PATH` (via mise).

### Terminal

| Key | Action |
|-----|--------|
| `<leader>tt` | Toggle floating terminal (works from inside too) |
| `<Esc><Esc>` (terminal) | Go to normal mode (snacks) |

### Diagnostics

| Key | Action |
|-----|--------|
| `<leader>e` / `<leader>q` | Line diagnostics float / send to loclist |

## Maintenance

- `:Pack update` — update plugins
- `require('nvim-treesitter').install({...})` — add parsers up front
- `nvim --startuptime /tmp/st.log` — profile startup (steady state ~45ms)

## Layout

```
init.lua              loader, leader, requires
lua/options.lua       options + perf (providers/builtins off, ts folds)
lua/keymaps.lua       general keymaps
lua/plugins/
  init.lua            vim.pack.add + require order
  blink.lua           completion
  colorscheme.lua     monokai-pro (pro filter)
  copilot.lua         Copilot inline suggestions
  fzf.lua             fuzzy finder + keymaps
  gitsigns.lua        git signs / blame / hunks
  icons.lua           mini.icons (+ devicons shim)
  lsp.lua             native LSP config + on-attach maps
  multicursor.lua     multicursor keymaps
  oil.lua             file explorer
  snacks.lua          QoL modules
  statusline.lua      mini.statusline
  surround.lua        mini.surround (add/delete/replace pairs)
  dial.lua            smart increment/decrement (per-filetype)
  treesitter.lua      parsers + highlight (auto-install on open)
  treesitter-textobjects.lua  named-function motions
  treesitter-incremental.lua  expand/shrink node selection
  treesitter-context.lua      sticky function/block header
```
