INSERT INTO parks (id, slug, name, base_url)
VALUES (
  '11111111-1111-1111-1111-111111111111',
  'nn',
  'Джунгли Сити — НН',
  'https://nn.jucity.ru'
)
ON CONFLICT (slug) DO NOTHING;

INSERT INTO park_locations (park_id, address_text, city, lat, lon)
VALUES (
  '11111111-1111-1111-1111-111111111111',
  'Нижний Новгород, Примерная ул., 1',
  'Нижний Новгород',
  56.2965,
  43.9361
);

INSERT INTO park_contacts (park_id, type, value, is_primary)
VALUES
  ('11111111-1111-1111-1111-111111111111', 'phone', '+7 (999) 000-00-00', true),
  ('11111111-1111-1111-1111-111111111111', 'email', 'info@example.com', false);

-- dow: 0=Mon ... 6=Sun
INSERT INTO park_opening_hours (park_id, dow, open_time, close_time, is_closed, note)
VALUES
  ('11111111-1111-1111-1111-111111111111', 0, '12:00', '22:00', false, null),
  ('11111111-1111-1111-1111-111111111111', 1, '10:00', '22:00', false, null),
  ('11111111-1111-1111-1111-111111111111', 2, '10:00', '22:00', false, null),
  ('11111111-1111-1111-1111-111111111111', 3, '10:00', '22:00', false, null),
  ('11111111-1111-1111-1111-111111111111', 4, '10:00', '22:00', false, null),
  ('11111111-1111-1111-1111-111111111111', 5, '10:00', '22:00', false, null),
  ('11111111-1111-1111-1111-111111111111', 6, '10:00', '22:00', false, null);

INSERT INTO park_transport (park_id, kind, text)
VALUES
  ('11111111-1111-1111-1111-111111111111', 'metro', 'Метро: Примерная (5 минут пешком)'),
  ('11111111-1111-1111-1111-111111111111', 'car', 'На машине: парковка рядом с входом');

INSERT INTO site_pages (park_id, key, path, absolute_url)
VALUES
  ('11111111-1111-1111-1111-111111111111', 'contact', '/contact/', null),
  ('11111111-1111-1111-1111-111111111111', 'rules', '/rules/', null),
  ('11111111-1111-1111-1111-111111111111', 'rules_pdf', '/wp-content/uploads/2025/02/pravila-parka_compressed.pdf', null),
  ('11111111-1111-1111-1111-111111111111', 'prices_tickets', '/prices/tickets/', null),
  ('11111111-1111-1111-1111-111111111111', 'prices_vr', '/prices/vr/', null),
  ('11111111-1111-1111-1111-111111111111', 'promotions', '/akczii/', null),
  ('11111111-1111-1111-1111-111111111111', 'gift_cards', '/gift-cards/', null),
  ('11111111-1111-1111-1111-111111111111', 'party_main', '/party/', null),
  ('11111111-1111-1111-1111-111111111111', 'graduation', '/prazdnik/graduation/', null),
  ('11111111-1111-1111-1111-111111111111', 'new_year_trees', '/novogodnie-utrenniki/', null),
  ('11111111-1111-1111-1111-111111111111', 'poster', '/events/', null),
  ('11111111-1111-1111-1111-111111111111', 'attractions', '/attractions/', null),
  ('11111111-1111-1111-1111-111111111111', 'restaurant', '/rest/', null),
  ('11111111-1111-1111-1111-111111111111', 'restaurant_menu_pdf', '/wp-content/uploads/2025/02/menyu-a4-nn-fevral_compressed.pdf', null),
  ('11111111-1111-1111-1111-111111111111', 'restaurant_season_menu_pdf', '/wp-content/uploads/2025/11/sezonnoe-menyu-nizhnij-novgorod.pdf', null)
ON CONFLICT (park_id, key) DO NOTHING;

INSERT INTO legal_documents (park_id, key, title, path, absolute_url)
VALUES
  ('11111111-1111-1111-1111-111111111111', 'rules', 'Правила посещения', '/rules/', null);
