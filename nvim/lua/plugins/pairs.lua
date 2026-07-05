-- mini.pairs: autopairs. Module of the already installed mini.nvim, so no extra
-- dependency. In insert mode: an opening bracket/quote inserts its pair, typing
-- the closing char over an existing one skips it, <BS> deletes both, and <CR>
-- splits the pair onto an indented line.
--
-- blink accepts completions with <C-y> (default preset), not <CR>, so mini.pairs'
-- <CR> mapping does not clash with completion.
require('mini.pairs').setup()
