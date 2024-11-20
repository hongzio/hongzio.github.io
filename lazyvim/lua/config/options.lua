-- Options are automatically loaded before lazy.nvim startup
-- Default options that are always set: https://github.com/LazyVim/LazyVim/blob/main/lua/lazyvim/config/options.lua
-- Add any additional options here

vim.api.nvim_create_autocmd("TextYankPost", {
  callback = function()
    local unnamed_register = vim.fn.getreg("*")
    require("vim.ui.clipboard.osc52").copy("*")(vim.split(unnamed_register, "\n"))
    local unnamedplus_register = vim.fn.getreg("+")
    require("vim.ui.clipboard.osc52").copy("+")(vim.split(unnamedplus_register, "\n"))
  end,
})
