return {
  "zbirenbaum/copilot.lua",
  enabled = false,
  cmd = "Copilot",
  build = ":Copilot auth",
  event = "InsertEnter",
  opts = {
    suggestion = {
      enabled = false,
      auto_trigger = false,
    },
    panel = { enabled = true },
    filetypes = {
      markdown = true,
      yaml = true,
      help = true,
    },
  },
}
