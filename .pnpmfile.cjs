"use strict";

const PRESET_NAME = "@umijs/preset-umi";
const PRESET_VERSION = "4.7.5";
const VITE_BUNDLER_NAME = "@umijs/bundler-vite";
const VITE_BUNDLER_VERSION = "4.7.5";

module.exports = {
  hooks: {
    readPackage(pkg) {
      if (pkg.name === "@nutui/nutui-react-taro") {
        if (pkg.version !== "3.0.20" || pkg.dependencies?.codesandbox !== "^2.2.3") {
          throw new Error("NutUI changed. Re-evaluate the unused CodeSandbox dependency removal before upgrading.");
        }
        const dependencies = { ...pkg.dependencies };
        delete dependencies.codesandbox;
        return { ...pkg, dependencies };
      }
      if (pkg.name !== PRESET_NAME) {
        return pkg;
      }

      if (pkg.version !== PRESET_VERSION) {
        throw new Error(
          `${PRESET_NAME} changed from ${PRESET_VERSION} to ${pkg.version}. Re-evaluate the Webpack-only security patch before upgrading.`,
        );
      }

      if (pkg.dependencies?.[VITE_BUNDLER_NAME] !== VITE_BUNDLER_VERSION) {
        throw new Error(
          `${PRESET_NAME}@${PRESET_VERSION} no longer resolves ${VITE_BUNDLER_NAME}@${VITE_BUNDLER_VERSION}. Re-evaluate and remove the security patch if upstream is fixed.`,
        );
      }

      const dependencies = { ...pkg.dependencies };
      delete dependencies[VITE_BUNDLER_NAME];
      return { ...pkg, dependencies };
    },
  },
};
