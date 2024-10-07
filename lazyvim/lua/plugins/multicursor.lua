return {
  "jake-stewart/multicursor.nvim",
  keys = {
    {
      "<up>",
      function()
        local mc = require("multicursor-nvim")
        local beforeCursorSize = 0
        mc.action(function(ctx)
          beforeCursorSize = #ctx.getCursors(ctx)
        end)
        mc.lineAddCursor(-1)
        local afterCursorSize = 0
        mc.action(function(ctx)
          afterCursorSize = #ctx.getCursors(ctx)
        end)
        mc.action(function(ctx)
          if beforeCursorSize == afterCursorSize then
            ctx:nextCursor(ctx:mainCursor():getPos()):delete()
          end
        end)
      end,
      mode = { "n", "v" },
      desc = "Add cursor above",
    },
    {
      "<down>",
      function()
        local mc = require("multicursor-nvim")
        local beforeCursorSize = 0
        mc.action(function(ctx)
          beforeCursorSize = #ctx.getCursors(ctx)
        end)
        mc.lineAddCursor(1)
        local afterCursorSize = 0
        mc.action(function(ctx)
          afterCursorSize = #ctx.getCursors(ctx)
        end)
        mc.action(function(ctx)
          if beforeCursorSize == afterCursorSize then
            ctx:prevCursor(ctx:mainCursor():getPos()):delete()
          end
        end)
      end,
      mode = { "n", "v" },
      desc = "Add cursor below",
    },
    -- {
    --   "<leader><up>",
    --   function()
    --     require("multicursor-nvim").lineSkipCursor(-1)
    --   end,
    --   mode = { "n", "v" },
    --   desc = "Skip cursor above",
    -- },
    -- {
    --   "<leader><down>",
    --   function()
    --     require("multicursor-nvim").lineSkipCursor(1)
    --   end,
    --   mode = { "n", "v" },
    --   desc = "Skip cursor below",
    -- },
    {
      "vm",
      function()
        require("multicursor-nvim").matchAddCursor(1)
      end,
      mode = { "n", "v" },
      desc = "Add cursor to next match",
    },
    {
      "vM",
      function()
        require("multicursor-nvim").deleteCursor()
      end,
      mode = { "n", "v" },
      desc = ""
    },
    -- {
    --   "<leader>s",
    --   function()
    --     require("multicursor-nvim").matchSkipCursor(1)
    --   end,
    --   mode = { "n", "v" },
    --   desc = "Skip cursor to next match",
    -- },
    -- {
    --   "<leader>N",
    --   function()
    --     require("multicursor-nvim").matchAddCursor(-1)
    --   end,
    --   mode = { "n", "v" },
    --   desc = "Add cursor to previous match",
    -- },
    -- {
    --   "<leader>S",
    --   function()
    --     require("multicursor-nvim").matchSkipCursor(-1)
    --   end,
    --   mode = { "n", "v" },
    --   desc = "Skip cursor to previous match",
    -- },
    -- {
    --   "<leader>x",
    --   function()
    --     require("multicursor-nvim").deleteCursor()
    --   end,
    --   mode = { "n", "v" },
    --   desc = "Delete cursor",
    -- },
    {
      "I",
      function()
        require("multicursor-nvim").insertVisual()
      end,
      mode = { "v" },
      desc = "Insert for each cursor",
    },
    {
      "A",
      function()
        require("multicursor-nvim").appendVisual()
      end,
      mode = { "v" },
      desc = "Append for each cursor",
    },
    {
      "<esc>",
      function()
        local mc = require("multicursor-nvim")
        if not mc.cursorsEnabled() then
          mc.disableCursors()
        elseif mc.hasCursors() then
          mc.clearCursors()
        else
          -- Default <esc> handler.
        end
      end,
      mode = { "n" },
    },
  },
  opts = {},
}
