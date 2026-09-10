self:
{
  config,
  lib,
  pkgs,
  ...
}:
{
  options.programs.admaster.enable = lib.mkEnableOption "the admaster command and its isolated REAPER runtime";
  config = lib.mkIf config.programs.admaster.enable {
    environment.systemPackages = [ self.packages.${pkgs.stdenv.hostPlatform.system}.admaster ];
  };
}
