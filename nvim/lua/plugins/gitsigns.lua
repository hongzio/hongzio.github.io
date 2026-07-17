-- gitsigns.nvim: git hunk signs, inline blame, and hunk-level actions.
require('gitsigns').setup({
  -- Inline blame on the current line, shown as virtual text at end of line.
  current_line_blame = true,
  current_line_blame_opts = {
    virt_text = true,
    virt_text_pos = 'eol',
    delay = 300,
    ignore_whitespace = false,
  },
  current_line_blame_formatter = '  <author>, <author_time:%Y-%m-%d> · <summary>',

  on_attach = function(bufnr)
    local gs = require('gitsigns')
    local function map(mode, lhs, rhs, desc)
      vim.keymap.set(mode, lhs, rhs, { buffer = bufnr, desc = desc })
    end

    -- Jump between hunks. target='all' so navigation also covers STAGED hunks
    -- (by default gitsigns only diffs working-tree vs index, so a staged change
    -- is no longer a hunk and would be skipped).
    map('n', ']h', function() gs.nav_hunk('next', { target = 'all' }) end, 'Next hunk (staged + unstaged)')
    map('n', '[h', function() gs.nav_hunk('prev', { target = 'all' }) end, 'Prev hunk (staged + unstaged)')

    -- Diff at cursor.
    map('n', '<leader>hp', gs.preview_hunk, 'Preview hunk (diff at cursor)')
    map('n', '<leader>hi', gs.preview_hunk_inline, 'Preview hunk inline')

    -- Reset the block (hunk) at cursor / whole buffer.
    map('n', '<leader>hr', gs.reset_hunk, 'Reset hunk')
    map('x', '<leader>hr', function() gs.reset_hunk({ vim.fn.line('.'), vim.fn.line('v') }) end, 'Reset selection')
    map('n', '<leader>hR', gs.reset_buffer, 'Reset buffer')

    -- Stage the block (hunk) at cursor / whole buffer / undo.
    map('n', '<leader>hs', gs.stage_hunk, 'Stage hunk')
    map('x', '<leader>hs', function() gs.stage_hunk({ vim.fn.line('.'), vim.fn.line('v') }) end, 'Stage selection')
    map('n', '<leader>hS', gs.stage_buffer, 'Stage buffer')
    map('n', '<leader>hu', gs.undo_stage_hunk, 'Undo stage hunk')

    -- Blame.
    map('n', '<leader>gb', function() gs.blame_line({ full = true }) end, 'Blame line (full)')
    map('n', '<leader>tb', gs.toggle_current_line_blame, 'Toggle inline blame')

    -- Diff whole file against index / last commit.
    map('n', '<leader>gd', gs.diffthis, 'Diff against index')
    map('n', '<leader>gD', function() gs.diffthis('~') end, 'Diff against last commit')

    -- Hunk text object: dih (delete hunk), vih (select hunk), etc.
    map({ 'o', 'x' }, 'ih', gs.select_hunk, 'Select hunk')
  end,
})
