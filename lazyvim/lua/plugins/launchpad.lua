return {
  "hongzio/launchpad.nvim",
  event = "VeryLazy",
  dependencies = {
    "MunifTanjim/nui.nvim",
    "grapp-dev/nui-components.nvim",
    "mfussenegger/nvim-dap",
    "nvim-telescope/telescope.nvim"
  },
  opts = {},
  keys = {
    {"<leader>R", function() end, desc="+Launchpad"},
    {"<leader>RC", function() require("launchpad").create_config("run") end, desc="Create run configuration", mode = {"n"}},
    {"<leader>RR", function() require("launchpad").show_configs("run") end, desc="Run configurations", mode = {"n"}},
    {"<leader>RD", function() require("launchpad").show_configs("debug") end, desc="Debug configurations", mode = {"n"}},
  },
}
