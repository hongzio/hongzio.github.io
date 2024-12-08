return {
  "zbirenbaum/copilot.lua",
  cmd = "Copilot",
  build = ":Copilot auth",
  event = {"InsertEnter", "CursorHoldI"},
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
