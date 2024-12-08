return {
  "hongzio/visidf.nvim",
  dependencies = {
    "mfussenegger/nvim-dap",
    "folke/snacks.nvim",
  },
  opts = {
    vdpath = "vd",
  },
  keys = {
    {
      "<leader>dv",
      function()
        require("visidf").run()
      end,
      desc = "visualize dataframe",
      mode = { "v" },
    },
    {
      "<leader>dV",
      function()
        require("visidf").prev()
      end,
      desc = "visualize previous dataframe",
      mode = { "n" },
    },
  },
}
