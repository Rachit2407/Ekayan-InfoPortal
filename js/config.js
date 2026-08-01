// js/config.js
// Supabase Project URL and Anon API Key (reused from Ekayan Bridge configuration)
const supabaseUrl = 'https://eolzuwwnusmtvssolavt.supabase.co';
const supabaseKey = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVvbHp1d3dudXNtdHZzc29sYXZ0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzk5NTAzMjIsImV4cCI6MjA5NTUyNjMyMn0.Zzu_LzCQzEZZtj3B3WD85-uWG6KMyGK1BlMxh4gbY60';

// Set to true when you want to switch from LocalStorage to Supabase cloud database
const USE_SUPABASE = false;

// Safe initialization that won't throw if script tag is missing
const supabaseClient = (USE_SUPABASE && supabaseUrl && supabaseKey && window.supabase) 
  ? window.supabase.createClient(supabaseUrl, supabaseKey) 
  : null;

window.USE_SUPABASE = USE_SUPABASE;
window.supabaseClient = supabaseClient;
