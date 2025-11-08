cssh() {
  local original_bg_spec
  local old_stty
  local exit_code
  old_stty=$(stty -g)
  stty -cbreak -echo time 1
  echo -ne "\e]11;?\a" >/dev/tty

  IFS=';' read -r -s -d $'\a' -t 1 _ original_bg_spec </dev/tty

  stty $old_stty

  if [[ -n "$original_bg_spec" ]]; then
    trap "echo -ne '\e]11;${original_bg_spec}\a'; trap - INT TERM EXIT" INT TERM EXIT
  fi

  echo -ne "\e]11;#3b0808\a"
  command ssh "$@"
  exit_code=$?

  return $exit_code
}
