module.exports = {
    uiHost: "0.0.0.0",
    uiPort: process.env.PORT || 1880,
    credentialSecret: process.env.NODERED_CREDENTIAL_SECRET || false,
    httpAdminRoot: "/",
    httpNodeRoot: "/api",
    functionGlobalContext: {},
    logging: { console: { level: "info", metrics: false, audit: true } },
    adminAuth: process.env.OIDC_ISSUER
        ? {
              type: "strategy",
              strategy: {
                  name: "openidconnect",
                  label: "Sign in with SSO",
                  icon: "fa-lock",
                  strategy: require("passport-openidconnect").Strategy,
                  options: {
                      issuer: process.env.OIDC_ISSUER,
                      authorizationURL: process.env.OIDC_AUTH_URL,
                      tokenURL: process.env.OIDC_TOKEN_URL,
                      userInfoURL: process.env.OIDC_USERINFO_URL,
                      clientID: process.env.OIDC_CLIENT_ID,
                      clientSecret: process.env.OIDC_CLIENT_SECRET,
                      callbackURL: process.env.OIDC_CALLBACK_URL,
                      scope: "profile email groups",
                      skipUserProfile: false,
                  },
                  verify: function () {
                      const args = Array.prototype.slice.call(arguments);
                      const done = args[args.length - 1];
                      const profile =
                          args.find(function (item) {
                              return (
                                  item &&
                                  typeof item === "object" &&
                                  !Array.isArray(item) &&
                                  (item.id || item.username || item.displayName || item.emails)
                              );
                          }) || {};
                      const username =
                          profile.username ||
                          profile.id ||
                          (profile.emails && profile.emails[0] && profile.emails[0].value) ||
                          "operator";
                      done(null, username);
                  },
              },
              users: function (username) {
                  return Promise.resolve({ username: username, permissions: "*" });
              },
          }
        : undefined,
};
