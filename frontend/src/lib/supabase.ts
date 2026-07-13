// src/lib/supabase.ts
import { createClient } from '@supabase/supabase-js'

const supabaseUrl  = process.env.NEXT_PUBLIC_SUPABASE_URL  || 'https://dummy.supabase.co'
const supabaseKey  = process.env.NEXT_PUBLIC_SUPABASE_KEY  || 'dummy-key'

export const supabase = createClient(supabaseUrl, supabaseKey)
