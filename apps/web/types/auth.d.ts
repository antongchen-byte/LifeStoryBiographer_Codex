import "next-auth";
import "next-auth/jwt";
declare module "next-auth" {
  interface User {
    backendToken?: string;
  }
}
declare module "next-auth/jwt" {
  interface JWT {
    backendToken?: string;
  }
}
