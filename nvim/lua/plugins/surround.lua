-- mini.surround: add/delete/replace surrounding pairs. Module of the already
-- installed mini.nvim, so no extra dependency.
--   gsa{motion}{char}  add surround     (e.g. gsaiw" -> wrap word in quotes)
--   gsd{char}          delete surround  (e.g. gsd")
--   gsr{old}{new}      replace surround (e.g. gsr"' )
--
-- Prefixed under `gs` (not the default `s`) so `s`/`S` stay free for flash.nvim.
require('mini.surround').setup({
  -- Honor the visual selection type: blockwise (<C-v>) wraps each row's column
  -- segment, linewise (V) puts the surroundings on their own indented lines.
  respect_selection_type = true,
  mappings = {
    add = 'gsa',
    delete = 'gsd',
    replace = 'gsr',
    find = 'gsf',
    find_left = 'gsF',
    highlight = 'gsh',
    update_n_lines = 'gsn',
  },
})
