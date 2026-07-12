# Supabase Authentication Setup

This backend uses Supabase Auth for identity and Neon PostgreSQL for app data.
Supabase owns signup, login, refresh tokens, and JWT issuance. The `students`
table stores the app profile and links to Supabase through `supabase_user_id`.

## Required Environment Variables

Add these values to `.env`:

```env
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_ANON_KEY=<anon-key>
SUPABASE_JWT_SECRET=<jwt-secret>
```

Optional:

```env
BACKEND_CORS_ORIGINS=http://localhost:3000,http://localhost:8000
```

## Supabase Dashboard

1. Create or open your Supabase project.
2. Go to Authentication > Providers.
3. Enable the Email provider.
4. For local hackathon development, disable email confirmation so
   `/auth/signup` returns a usable session immediately.
5. Set the Site URL to your frontend origin, such as `http://localhost:3000`.

## API Flow

1. `POST /auth/signup` creates a Supabase Auth user and a matching `students`
   profile.
2. `POST /auth/login` returns Supabase access and refresh tokens.
3. `GET /auth/me` verifies the Bearer token and returns the linked student.
4. `POST /auth/refresh` exchanges a refresh token for fresh tokens.

Keep all Supabase secrets out of git. `.env` is already gitignored.
