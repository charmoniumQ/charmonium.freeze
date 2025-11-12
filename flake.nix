{
inputs = {
    flake-utils = {
      url = "github:numtide/flake-utils";
    };
    nixpkgs = {
      url = "github:NixOS/nixpkgs";
    };
    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, flake-utils, pyproject-nix, uv2nix, pyproject-build-systems }:
    let
      project = pyproject-nix.lib.project.loadPyproject {
        # Read & unmarshal pyproject.toml relative to this project root.
        # projectRoot is also used to set `src` for renderers such as buildPythonPackage.
        projectRoot = ./.;
      };
      workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };
      overlay = workspace.mkPyprojectOverlay {
        sourcePreference = "wheel";
      };
    in flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python313;
        other-pythons = {
          py310 = pkgs.python310;
          py311 = pkgs.python311;
          py312 = pkgs.python312;
          py313 = pkgs.python313;
        };
        pythonSets = python: (pkgs.callPackage pyproject-nix.build.packages {
          inherit python;
        }).overrideScope
          (
            pkgs.lib.composeManyExtensions [
              pyproject-build-systems.overlays.wheel
              overlay
            ]
          );
      in rec {
        devShells = rec {
          impure = pkgs.mkShell {
            packages = [
              pkgs.hatch
              pkgs.uv
              python
            ] ++ other-pythons;
            env = {
              # Prevent uv from managing Python downloads
              UV_PYTHON_DOWNLOADS = "never";
              # Force uv to use nixpkgs Python interpreter
              UV_PYTHON = python.interpreter;
            }
            // pkgs.lib.optionalAttrs pkgs.stdenv.isLinux {
              # Python libraries often load native shared objects using dlopen(3).
              # Setting LD_LIBRARY_PATH makes the dynamic library loader aware of libraries without using RPATH for lookup.
              LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath pkgs.pythonManylinuxPackages.manylinux1;
            };
            shellHook = ''
              unset PYTHONPATH
              source .venv/bin/activate
            '';
          };
          default = impure;
        };
        packages = builtins.mapAttrs (
          py-name:
          python:
          python.pkgs.buildPythonPackage (pyproject-nix.lib.renderers.buildPythonPackage {
            inherit project python;
          })
        )
          other-pythons;
      });
}
