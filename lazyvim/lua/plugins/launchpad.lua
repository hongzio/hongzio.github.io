return {
  "hongzio/launchpad.nvim",
  lazy = false,
  dependencies = {
    "MunifTanjim/nui.nvim",
    "grapp-dev/nui-components.nvim"
  },
  opts = {},
  keys = {
    {"<leader>R", function() end, desc="+Launchpad"},
    {"<leader>RC", function() require("launchpad").create_config("run") end, desc="Create run configuration", mode = {"n"}},
    {"<leader>RR", function() require("launchpad").show_configs("run") end, desc="Run configurations", mode = {"n"}},
  },
}
