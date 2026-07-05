-- nvim-treesitter (main branch). This branch is intentionally minimal: it
-- installs parsers and exposes vim.treesitter; highlighting is started per
-- buffer via an autocmd.
local ts = require('nvim-treesitter')

ts.setup()

-- Parsers to keep installed up-front (common filetypes seen at startup).
local ensure = {
  'lua', 'luadoc', 'vim', 'vimdoc', 'query',
  'bash', 'markdown', 'markdown_inline',
  'json', 'yaml', 'toml',
}

-- [perf] Only spawn the (async) installer for parsers that are actually
-- missing, so steady-state startup does zero treesitter work.
local installed = ts.get_installed('parsers')
local missing = vim.tbl_filter(function(lang)
  return not vim.list_contains(installed, lang)
end, ensure)
if #missing > 0 then
  ts.install(missing)
end

-- Enable treesitter highlighting + indentation for a buffer.
local function start(buf, lang)
  if vim.treesitter.language.add(lang) then
    pcall(vim.treesitter.start, buf, lang)
    vim.bo[buf].indentexpr = "v:lua.require'nvim-treesitter'.indentexpr()"
  end
end

-- Auto-install the parser the first time a filetype is opened, then start
-- highlighting once it finishes compiling. This means any language "just works"
-- (e.g. go, python, rust) without maintaining a list — and never crashes a
-- buffer that has no parser.
local installing = {}
vim.api.nvim_create_autocmd('FileType', {
  callback = function(args)
    local buf = args.buf
    local lang = vim.treesitter.language.get_lang(vim.bo[buf].filetype)
    if not lang then return end

    if vim.list_contains(ts.get_installed('parsers'), lang) then
      start(buf, lang)
    elseif not installing[lang] and vim.list_contains(ts.get_available(), lang) then
      installing[lang] = true
      local ok, task = pcall(ts.install, { lang })
      if ok and type(task) == 'table' and task.await then
        task:await(vim.schedule_wrap(function(err)
          installing[lang] = nil
          if not err and vim.api.nvim_buf_is_valid(buf) then
            start(buf, lang)
          end
        end))
      else
        installing[lang] = nil
      end
    end
  end,
})
