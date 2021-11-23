{
  inputs.flake-utils.url = "github:numtide/flake-utils";

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        name = "charmonium-determ-hash";
        name-shell = "${name}-shell";
        name-test = "${name}-test";
        default-python = pkgs.python39;
        # Alternative Pythons for Tox
        alternative-pythons = [
          pkgs.python37
          pkgs.python38
          pkgs.python39
          pkgs.python310
        ];
      in {
        packages.${name} = pkgs.poetry2nix.mkPoetryApplication {
          projectDir = ./.;
          python = default-python;
        };
        packages.${name-shell} = pkgs.mkShell {
          buildInputs = alternative-pythons ++ [
            pkgs.poetry
            # (pkgs.poetry2nix.mkPoetryEnv {
            #   projectDir = ./.;
            #   # default Python for shell
            #   python = default-python;
            # })
          ];
          # TODO: write a check expression (`nix flake check`)
        };
        devShell = self.packages.${system}.${name-shell};
        defaultPackage = self.packages.${system}.${name};
      });
}
