import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";

const api = process.env.API_INTERNAL_URL ?? "http://localhost:8000";
export const { handlers, auth, signIn, signOut } = NextAuth({
  trustHost: true,
  pages: { signIn: "/login" },
  session: { strategy: "jwt", maxAge: 7 * 24 * 3600 },
  providers: [
    Credentials({
      credentials: { email: {}, password: {} },
      async authorize(credentials) {
        const response = await fetch(`${api}/api/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: credentials.email,
            password: credentials.password,
          }),
        });
        if (!response.ok) return null;
        const data = await response.json();
        return { ...data.user, backendToken: data.token };
      },
    }),
  ],
  callbacks: {
    jwt({ token, user }) {
      if (user) token.backendToken = user.backendToken;
      return token;
    },
    session({ session, token }) {
      if (session.user && token.sub) session.user.id = token.sub;
      return session;
    },
  },
  events: {
    async signOut(message) {
      if ("token" in message && message.token?.backendToken) {
        await fetch(`${api}/api/auth/logout`, {
          method: "POST",
          headers: { Authorization: `Bearer ${message.token.backendToken}` },
        }).catch(() => {});
      }
    },
  },
});
