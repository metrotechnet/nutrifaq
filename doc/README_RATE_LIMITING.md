# Nutria Agent – Documentation
# Rate Limiting Configuration 🛡️

Ce document décrit la configuration de la limitation de débit (rate limiting) pour le projet **Nutria Agent**. Il explique comment protéger l'application contre les abus et les attaques, et détaille les paramètres utilisés dans ce projet.

Ce document explique la configuration de rate limiting (limitation de débit) mise en place pour protéger l'application contre les abus et les attaques.

## Vue d'ensemble

**Niveau de protection:** Niveau 1 - Minimal (Gratuit)

Le système utilise une approche multi-couches:
1. **Rate limiting par IP** avec slowapi
2. **Rate limiting par session** pour suivre les utilisateurs individuels
3. **Debouncing frontend** pour éviter les requêtes accidentelles

## Configuration actuelle

### 1. Limites Globales (Par IP)

Configurées dans `app.py`:
```python
limiter = Limiter(
    key_func=get_remote_address, 
    default_limits=["300 per day", "100 per hour"]
)
```

**Signification:**
- Maximum 300 requêtes par jour par adresse IP
- Maximum 100 requêtes par heure par adresse IP

### 2. Limites par Endpoint

#### `/query` - Questions à l'agent
```python
@limiter.limit("10/hour")  # Max 10 questions par heure
```

**Raison:** Limite stricte pour contrôler les coûts API et éviter les abus

#### `/api/tts` - Text-to-Speech
```python
@limiter.limit("10/hour")  # Max 10 requêtes TTS par heure
```

**Raison:** TTS est coûteux (utilise API OpenAI payante), limite stricte pour contrôler les coûts

### 3. Limites par Session

Implémentées dans `api/sessions.py`:
```python
def is_session_rate_limited(session_id: str, max_requests_per_hour: int = 50):
    # Compte les messages utilisateur de la dernière heure
    # Retourne True si >= 50 requêtes
```

**Avantages:**
- Suit les utilisateurs même s'ils changent d'IP (mobile/WiFi)
- Limite par conversation individuelle
- Plus précis que le rate limiting par IP seul

### 4. Debouncing Frontend

Implémenté dans `static/js/chat.js`:
```javascript
const MIN_REQUEST_INTERVAL = 2000; // 2 secondes minimum entre requêtes

// Dans sendMessage():
if (now - lastRequestTime < MIN_REQUEST_INTERVAL) {
    // Bloquer et afficher feedback visuel
    return;
}
```

**Avantages:**
- Empêche les clics accidentels multiples
- Feedback visuel immédiat (bordure orange)
- Réduit la charge serveur inutile

## Réponses Rate Limit

### Quand un utilisateur dépasse les limites:

**Backend (429 Too Many Requests):**
```json
{
  "error": "Rate limit exceeded",
  "message": "Trop de requêtes. Veuillez patienter quelques instants."
}
```

**Frontend:**
- Bordure orange sur l'input box
- Message console: "Please wait before sending another message"
- Pas de requête envoyée

## Monitoring

### Vérifier les rate limits

1. **Logs Cloud Run:**
```bash
gcloud run logs read --service=imx-multi-agent --limit=100 | grep "Rate limit"
```

2. **Tester les limites:**
```bash
# Tester limite /query (10/heure)
for i in {1..15}; do
  curl -X POST https://your-app.run.app/query \
    -H "Content-Type: application/json" \
    -d '{"question": "test", "language": "fr"}' &
done

# Vous devriez voir des erreurs 429 après la 10ème requête
```

### Métriques à surveiller

Dans GCP Console → Cloud Run → Metrics:
- **Request count** - Augmentation soudaine = possible attaque
- **Error rate** - Beaucoup de 429 = utilisateurs légitimes impactés
- **Response time** - Ralentissement = possible surcharge

## Ajustement des limites

### Augmenter les limites pour /query

Si les utilisateurs légitimes sont bloqués:

**Option 1 - Augmenter la limite par minute:**
```python
# Dans api/routes/query.py
@limiter.limit("50/minute")  # Était 30/minute
```

**Option 2 - Ajuster la limite de session:**
```python
# Dans api/sessions.py
is_session_rate_limited(session_id, max_requests_per_hour=100)  # Était 50
```

### Réduire les limites TTS

Si les coûts sont trop élevés:
```python
# Dans api/routes/tts.py
@limiter.limit("5/hour")  # Était 10/hour
```

### Ajuster le debouncing

Si trop restrictif pour les utilisateurs:
```javascript
// Dans static/js/chat.js
const MIN_REQUEST_INTERVAL = 1000; // 1 seconde au lieu de 2
```

## Évolution vers Niveau 2

Si vous avez besoin de plus de contrôle:

### Option 1: Redis pour rate limiting partagé

**Pourquoi:** Limites partagées entre toutes les instances Cloud Run

```python
# Dans app.py
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="redis://YOUR_REDIS_IP:6379"
)
```

**Coût:** ~$5-10/mois pour Redis Memorystore (GCP)

### Option 2: Access Key Authentication

**Pourquoi:** Distribuer des clés d'accès uniques aux clients

```python
# Vérifier la clé dans chaque requête
if request.headers.get('X-Access-Key') != expected_key:
    return JSONResponse({"error": "Unauthorized"}, status_code=401)
```

**Avantages:**
- Traçabilité par client
- Révocation possible
- Quotas personnalisés

### Option 3: Google Cloud Armor

**Pourquoi:** Protection DDoS professionnelle au niveau infrastructure

**Coût:** ~$1-5/mois selon trafic

**Fonctionnalités:**
- Rate limiting au niveau Load Balancer
- Blocage géographique
- Protection contre bots
- Règles WAF

## Cas d'usage

### Utilisateur normal
- **10 questions/heure** = Usage modéré et contrôlé
- **Debouncing 2s** = Imperceptible
- **10 TTS/heure** = Suffisant pour écouter réponses importantes

### Attaquant
- **10 requêtes/heure** bloqué rapidement
- **300/jour** bloqué après ~30 heures d'attaque continue
- **Session tracking** détecte comportement anormal

### Bot scraper
- **Debouncing** rend le scraping lent
- **Rate limit IP** bloque rapidement
- **Session limit** détecte absence de session valide

## Dépannage

### Erreur "Rate limit exceeded" pour utilisateurs légitimes

**Cause possible:** Plusieurs utilisateurs derrière même IP (entreprise, université)

**Solution:**
1. Augmenter limite par IP: `limiter.limit("50/minute")`
2. Implémenter authentification par utilisateur
3. Utiliser cookies/session pour identifier utilisateurs uniques

### Rate limit ne fonctionne pas

**Vérifications:**
```bash
# 1. Vérifier que slowapi est installé
pip list | grep slowapi

# 2. Vérifier que limiter est dans app.state
# Dans app.py, doit avoir:
app.state.limiter = limiter

# 3. Tester manuellement
curl -v https://your-app.run.app/query  # Regarder headers X-RateLimit-*
```

### Trop de 429 errors dans les logs

**Possible:** Limite trop stricte

**Analyse:**
1. Regarder patterns dans logs (même IP? Heures similaires?)
2. Vérifier si utilisateurs légitimes ou attaque
3. Ajuster limites en conséquence

## Bonnes pratiques

### ✅ À faire
- Monitorer régulièrement les logs
- Ajuster limites selon usage réel
- Informer utilisateurs des limites
- Tester les limites avant déploiement
- Documenter tout changement

### ❌ À éviter
- Limites trop strictes (frustre utilisateurs)
- Limites trop permissives (risque d'abus)
- Pas de monitoring (attaques non détectées)
- Changer limites sans tester
- Oublier de redéployer après changements

## Tests

### Test manuel des limites

```bash
# Test /query limit (30/minute)
echo "Testing query rate limit..."
for i in {1..35}; do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST https://your-app.run.app/query \
    -H "Content-Type: application/json" \
    -d '{"question":"test","language":"fr","session_id":"test-session"}'
  sleep 1
done
# Devrait voir 200 x30 puis 429 x5

# Test /api/tts limit (10/hour)
echo "Testing TTS rate limit..."
for i in {1..12}; do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST https://your-app.run.app/api/tts \
    -H "Content-Type: application/json" \
    -d '{"text":"test","language":"fr"}'
done
# Devrait voir 200 x10 puis 429 x2
```

### Test automatisé (Python)

```python
import requests
import time

def test_rate_limit():
    url = "https://your-app.run.app/query"
    results = []
    
    for i in range(35):
        resp = requests.post(url, json={
            "question": f"test {i}",
            "language": "fr",
            "session_id": "test-session"
        })
        results.append(resp.status_code)
        time.sleep(1)
    
    success = results.count(200)
    rate_limited = results.count(429)
    
    print(f"✅ Success: {success}")
    print(f"⛔ Rate limited: {rate_limited}")
    
    assert success == 30, f"Expected 30 success, got {success}"
    assert rate_limited == 5, f"Expected 5 rate limited, got {rate_limited}"

if __name__ == "__main__":
    test_rate_limit()
```

## Résumé

**Protection actuelle:**
- ✅ Rate limiting par IP (slowapi)
- ✅ Rate limiting par session
- ✅ Frontend debouncing
- ✅ Limites par endpoint
- ✅ Gratuit (pas de Redis/Cloud Armor)

**Efficacité:**
- 🛡️ Protège contre scripts simples
- 🛡️ Limite les coûts API
- 🛡️ Empêche spam accidentel
- ⚠️ Ne protège PAS contre DDoS distribué
- ⚠️ Limites par IP pas idéales pour IP partagées

**Prochaines étapes (si nécessaire):**
1. Redis Memorystore pour rate limiting distribué
2. Access Key authentication
3. Google Cloud Armor pour DDoS protection
4. Budget alerts dans GCP
