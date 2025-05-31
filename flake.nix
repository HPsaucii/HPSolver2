{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs";
    flake-utils.url = "github:numtide/flake-utils";
  };
  outputs = {
    self,
    nixpkgs,
    flake-utils,
  }:
    flake-utils.lib.eachDefaultSystem (
      system: let
        pkgs = import nixpkgs {
          inherit system;
        };
      in
        with pkgs; {
          devShells.default = mkShell {
            buildInputs = with python312Packages;
              [
                python
                tkinter
                customtkinter
                keyboard
                ctypesgen
                pillow
                mss
                numpy
                opencv4
                pytesseract
                scikit-image
                tensorflow
                keras
                evdev
                pyinstaller
              ]
              ++ [
                xorg.xprop
                xdotool
                tesseract
                grim
              ];
          };
        }
    );
}
