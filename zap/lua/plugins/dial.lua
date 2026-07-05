-- dial.nvim: smarter <C-a>/<C-x>. Beyond numbers it cycles dates, booleans,
-- logical/comparison operators, weekdays, months, etc., picking the rule group
-- by filetype (falls back to `default`). Ported from the LazyVim spec.
local augend = require('dial.augend')

-- Reusable constant augends (shared across filetype groups).
local logical_operators = augend.constant.new({
  elements = { '&&', '||' }, word = false, cyclic = true,
})
local equal_operators = augend.constant.new({
  elements = { '==', '!=' }, word = false, cyclic = true,
})
local compare_operators = augend.constant.new({
  elements = { '<', '>', '<=', '>=' }, word = false, cyclic = true,
})
local logical_words = augend.constant.new({
  elements = { 'and', 'or' }, word = true, cyclic = true,
})
local capitalized_boolean = augend.constant.new({
  elements = { 'True', 'False' }, word = true, cyclic = true,
})
local ordinal_numbers = augend.constant.new({
  elements = {
    'first', 'second', 'third', 'fourth', 'fifth',
    'sixth', 'seventh', 'eighth', 'ninth', 'tenth',
  },
  word = false, cyclic = true,
})
local weekdays = augend.constant.new({
  elements = {
    'Monday', 'Tuesday', 'Wednesday', 'Thursday',
    'Friday', 'Saturday', 'Sunday',
  },
  word = true, cyclic = true,
})
local months = augend.constant.new({
  elements = {
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
  },
  word = true, cyclic = true,
})

require('dial.config').augends:register_group({
  default = {
    augend.integer.alias.decimal,      -- 0, 1, 2, ...
    augend.integer.alias.hex,          -- 0x01, 0x1a1f, ...
    augend.date.alias['%Y/%m/%d'],     -- 2022/02/19
    ordinal_numbers,
    weekdays,
    months,
  },
  typescript = {
    augend.integer.alias.decimal,
    augend.constant.alias.bool,        -- true <-> false
    logical_operators,
    augend.constant.new({ elements = { 'let', 'const' } }),
  },
  yaml = {
    augend.integer.alias.decimal,
    augend.constant.alias.bool,
  },
  css = {
    augend.integer.alias.decimal,
    augend.hexcolor.new({ case = 'lower' }),
    augend.hexcolor.new({ case = 'upper' }),
  },
  markdown = {
    augend.misc.alias.markdown_header,
  },
  json = {
    augend.integer.alias.decimal,
    augend.semver.alias.semver,        -- v1.1.2
  },
  lua = {
    augend.integer.alias.decimal,
    augend.constant.alias.bool,
    augend.constant.new({ elements = { 'and', 'or' }, word = true, cyclic = true }),
  },
  python = {
    augend.integer.alias.decimal,
    capitalized_boolean,
    logical_words,
    equal_operators,
    compare_operators,
    augend.integer.alias.hex,
    augend.date.alias['%Y/%m/%d'],
    ordinal_numbers,
    weekdays,
    months,
  },
  go = {
    augend.integer.alias.decimal,
    logical_operators,
    equal_operators,
    compare_operators,
    augend.constant.alias.bool,
    augend.integer.alias.hex,
    augend.date.alias['%Y/%m/%d'],
    ordinal_numbers,
    weekdays,
    months,
  },
  sh = {
    augend.integer.alias.decimal,
    augend.integer.alias.hex,
    augend.constant.alias.bool,        -- lowercase true <-> false (shell)
  },
})

-- Map filetype -> group name; anything unlisted uses `default`.
vim.g.dials_by_ft = {
  css = 'css',
  javascript = 'typescript',
  javascriptreact = 'typescript',
  json = 'json',
  lua = 'lua',
  markdown = 'markdown',
  python = 'python',
  sh = 'sh',
  bash = 'sh',
  sass = 'css',
  scss = 'css',
  typescript = 'typescript',
  typescriptreact = 'typescript',
  yaml = 'yaml',
  go = 'go',
}

-- <C-a>/<C-x> (normal + visual) and g<C-a>/g<C-x> (visual, per-line ramp), each
-- resolving the group from the current buffer's filetype.
local function bind(key, fn, mode)
  vim.keymap.set(mode, key, function()
    return require('dial.map')[fn](vim.g.dials_by_ft[vim.bo.filetype] or 'default')
  end, { expr = true, desc = 'dial ' .. fn })
end
bind('<C-a>', 'inc_normal', 'n')
bind('<C-x>', 'dec_normal', 'n')
bind('<C-a>', 'inc_visual', 'v')
bind('<C-x>', 'dec_visual', 'v')
bind('g<C-a>', 'inc_gvisual', 'v')
bind('g<C-x>', 'dec_gvisual', 'v')
