return {
  "nvim-telescope/telescope.nvim",
  keys = {
    {
      "<leader>fh",
      "<CMD>Telescope find_files find_command=rg,--ignore,--hidden,--files,-u<CR>",
      desc = "Find files (hidden)",
    }
  }
}
