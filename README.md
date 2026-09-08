# THYSMY Fundamental Web V3 Starter

V3 adds login, Free/Pro access, ToyyibPay payment structure, Supabase database/auth and Admin Panel on top of the V2.5 fundamental engine.

## Demo preview
Default `DEMO_MODE=true`.
- Pro: `demo@thysmy.local` / `demo12345`
- Admin: `admin@thysmy.local` / `demo12345`

## Production setup
1. Create a Supabase project.
2. Run `SUPABASE_SETUP.sql` in Supabase SQL Editor.
3. Put Supabase URL, anon key and service-role key in Render Environment Variables.
4. Set `ADMIN_EMAIL`.
5. Create a ToyyibPay Sandbox account at dev.toyyibpay.com and create a Category.
6. Set ToyyibPay Secret Key + Category Code in Render.
7. Set `APP_BASE_URL` to your public Render URL.
8. Test Sandbox payments. ToyyibPay callback cannot reach localhost.
9. Set `DEMO_MODE=false`.
10. For real payments set `TOYYIBPAY_MODE=production` and production credentials.

## Plan
- Free RM0
- Pro RM29 / 30 days

Never commit service-role or ToyyibPay secrets to GitHub.
