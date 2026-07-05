-- mini.surround: add/delete/replace surrounding pairs. Module of the already
-- installed mini.nvim, so no extra dependency.
--   sa{motion}{char}  add surround     (e.g. saiw" -> wrap word in quotes)
--   sd{char}          delete surround  (e.g. sd")
--   sr{old}{new}      replace surround (e.g. sr"' )
require('mini.surround').setup({
  -- Honor the visual selection type: blockwise (<C-v>) wraps each row's column
  -- segment, linewise (V) puts the surroundings on their own indented lines.
  respect_selection_type = true,
})
