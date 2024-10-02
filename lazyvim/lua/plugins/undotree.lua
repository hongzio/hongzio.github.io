return {
  "jiaoshijie/undotree",
  dependencies = "nvim-lua/plenary.nvim",
  opts = true,
  keys = {
    {
      "<leader>UU",
      function()
        require("undotree").toggle()
      end,
      desc = "UndoTree",
    },
  },
}
