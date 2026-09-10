{
  description = "Natural-speed REAPER podcast ad mastering";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      each = nixpkgs.lib.genAttrs systems;
      pkgsFor =
        system:
        import nixpkgs {
          inherit system;
          config.allowUnfreePredicate =
            pkg:
            builtins.elem (nixpkgs.lib.getName pkg) [
              "reaper"
              "admaster"
            ];
        };
    in
    {
      packages = each (
        system:
        let
          pkgs = pkgsFor system;
        in
        rec {
          admaster = pkgs.callPackage ./nix/package.nix { };
          default = admaster;
        }
      );
      apps = each (system: {
        default = {
          type = "app";
          meta.description = "Master a spoken-word ad at natural speed";
          program = "${self.packages.${system}.admaster}/bin/admaster";
        };
      });
      devShells = each (
        system:
        let
          pkgs = pkgsFor system;
        in
        {
          default = pkgs.mkShell {
            inputsFrom = [ self.packages.${system}.admaster ];
            packages = [
              self.packages.${system}.admaster
              pkgs.git
              pkgs.gh
              pkgs.lua5_4
              pkgs.nixfmt
              pkgs.ruff
              pkgs.shellcheck
            ];
          };
        }
      );
      checks = each (
        system:
        import ./nix/checks.nix {
          pkgs = pkgsFor system;
          package = self.packages.${system}.admaster;
        }
      );
      nixosModules.default = import ./nix/module.nix self;
      formatter = each (system: (pkgsFor system).nixfmt);
    };
}
