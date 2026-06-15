from django.shortcuts import render, redirect
from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone
from django.db import models
from datetime import datetime, timedelta
from .models import Membre, Administrateur, Terrain, Reservation, BlocageTerrain
from django.http import JsonResponse
from requests_oauthlib import OAuth2Session


# ============================================================
# DÉCORATEUR : vérifie que l'utilisateur est admin
# Redirige vers l'accueil si ce n'est pas le cas
# ============================================================
def admin_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.session.get('membre_id'):
            return redirect('login')
        if not request.session.get('is_admin'):
            return redirect('accueil')
        return view_func(request, *args, **kwargs)
    return wrapper

# ============================================================
# LOGIN
# Authentification via numéro d'affiliation + mot de passe
# Vérifie que le membre est actif (en ordre de cotisation)
# ============================================================
def login_view(request):
    if request.method == 'POST':
        numero   = request.POST.get('numero')
        password = request.POST.get('password')

        try:
            membre = Membre.objects.get(pk=numero)
        except Membre.DoesNotExist:
            return render(request, 'tennis/login.html', {'erreur': 'Numéro d\'affiliation inconnu.'})

        # Vérifie le mot de passe hashé
        if not check_password(password, membre.password):
            return render(request, 'tennis/login.html', {'erreur': 'Mot de passe incorrect.'})

        # Vérifie que le membre est en ordre de cotisation
        if not membre.actif:
            return render(request, 'tennis/login.html', {'erreur': 'Votre compte n\'est pas actif. Contactez un administrateur.'})

        # Stocke les informations du membre en session
        request.session['membre_id']  = membre.numero_affiliation
        request.session['membre_nom'] = f"{membre.prenom} {membre.nom}"
        request.session['is_admin']   = Administrateur.objects.filter(pk=numero).exists()

        # Première connexion → redirection vers changement de mot de passe
        if membre.premiere_connexion:
            return redirect('changer_password')

        return redirect('accueil')

    return render(request, 'tennis/login.html')

# ============================================================
# LOGOUT
# Vide la session et redirige vers le login
# ============================================================
def logout_view(request):
    request.session.flush()
    return redirect('login')

# ============================================================
# ACCUEIL
# Page d'accueil après connexion
# ============================================================
def accueil(request):
    if not request.session.get('membre_id'):
        return redirect('login')
    return render(request, 'tennis/accueil.html')

# ============================================================
# CHANGER MOT DE PASSE (première connexion)
# Obligatoire lors de la première connexion
# ============================================================
def changer_password(request):
    if not request.session.get('membre_id'):
        return redirect('login')

    if request.method == 'POST':
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')

        if password1 != password2:
            return render(request, 'tennis/changer_password.html',
                         {'erreur': 'Les mots de passe ne correspondent pas.'})

        if len(password1) < 6:
            return render(request, 'tennis/changer_password.html',
                         {'erreur': 'Le mot de passe doit contenir au moins 6 caractères.'})

        # Met à jour le mot de passe et désactive la première connexion
        membre = Membre.objects.get(pk=request.session['membre_id'])
        membre.password = make_password(password1)
        membre.premiere_connexion = False
        membre.save()

        return redirect('accueil')

    return render(request, 'tennis/changer_password.html')

# ============================================================
# LISTE DES MEMBRES
# Affiche les membres actifs avec filtres par classement et recherche
# Pagination : 10 membres par page
# ============================================================
def liste_membres(request):
    if not request.session.get('membre_id'):
        return redirect('login')

    # Récupère les paramètres de filtrage
    classement = request.GET.get('classement', '')
    search     = request.GET.get('search', '')

    # Membres actifs triés alphabétiquement
    membres = Membre.objects.filter(actif=True).order_by('nom', 'prenom')

    # Applique les filtres
    if classement:
        membres = membres.filter(classement=classement)

    if search:
        membres = membres.filter(
            models.Q(nom__icontains=search) |
            models.Q(prenom__icontains=search)
        )

    # Pagination : 10 membres par page
    from django.core.paginator import Paginator
    paginator   = Paginator(membres, 10)
    page_number = request.GET.get('page')
    page_obj    = paginator.get_page(page_number)

    return render(request, 'tennis/liste_membres.html', {
        'page_obj': page_obj,
        'classements': Membre.CLASSEMENTS,
        'classement_selectionne': classement,
        'search': search,
    })

# ============================================================
# MES RÉSERVATIONS
# Affiche les réservations du membre connecté
# Indique si la suppression est encore possible (> 24h avant)
# ============================================================
def mes_reservations(request):
    if not request.session.get('membre_id'):
        return redirect('login')

    membre = Membre.objects.get(pk=request.session['membre_id'])
    reservations = Reservation.objects.filter(membre=membre).order_by('date', 'heure_debut')

    # Calcule si chaque réservation peut encore être supprimée (24h avant)
    now = timezone.now()
    for r in reservations:
        debut = datetime.combine(r.date, r.heure_debut)
        debut = timezone.make_aware(debut)
        r.peut_supprimer = (debut - now) > timedelta(hours=24)

    return render(request, 'tennis/mes_reservations.html', {
        'reservations': reservations,
    })

# ============================================================
# SUPPRIMER UNE RÉSERVATION
# Possible uniquement si la réservation est à plus de 24h
# ============================================================
def supprimer_reservation(request, reservation_id):
    if not request.session.get('membre_id'):
        return redirect('login')

    reservation = Reservation.objects.get(pk=reservation_id)

    # Vérifie que la réservation appartient bien au membre connecté
    if reservation.membre.numero_affiliation != request.session['membre_id']:
        return redirect('mes_reservations')

    # Vérifie le délai de 24h avant suppression
    now   = timezone.now()
    debut = datetime.combine(reservation.date, reservation.heure_debut)
    debut = timezone.make_aware(debut)

    if (debut - now) > timedelta(hours=24):
        reservation.delete()

    return redirect('mes_reservations')

# ============================================================
# FAIRE UNE RÉSERVATION
# Simple : 1h avec 1 partenaire
# Double : 2h avec 3 partenaires
# Limites : 2h/semaine en simple, 4h/semaine en double
# ============================================================
def faire_reservation(request):
    if not request.session.get('membre_id'):
        return redirect('login')

    membre       = Membre.objects.get(pk=request.session['membre_id'])
    terrains     = Terrain.objects.all()
    membres_actifs = Membre.objects.filter(actif=True).exclude(pk=membre.numero_affiliation)

    # Créneaux horaires disponibles (9h à 22h)
    creneaux = [f"{h:02d}:00" for h in range(9, 22)]
    erreur   = None

    if request.method == 'POST':
        terrain_id  = request.POST.get('terrain')
        date        = request.POST.get('date')
        heure       = request.POST.get('heure')
        type_jeu    = request.POST.get('type_jeu')
        partenaire1 = request.POST.get('partenaire1')
        partenaire2 = request.POST.get('partenaire2')
        partenaire3 = request.POST.get('partenaire3')

        terrain   = Terrain.objects.get(pk=terrain_id)
        date_obj  = datetime.strptime(date, '%Y-%m-%d').date()
        heure_obj = datetime.strptime(heure, '%H:%M').time()

        # Vérifie que le terrain n'est pas déjà réservé
        deja_reserve = Reservation.objects.filter(
            terrain=terrain, date=date_obj, heure_debut=heure_obj
        ).exists()

        # Vérifie que le terrain n'est pas bloqué par un admin
        terrain_bloque = BlocageTerrain.objects.filter(
            terrain=terrain,
            date=date_obj,
            heure_debut__lte=heure_obj,
            heure_fin__gt=heure_obj
        ).exists()

        if deja_reserve:
            erreur = "Ce terrain est déjà réservé à cette heure."
        elif terrain_bloque:
            erreur = "Ce terrain est bloqué à cette heure (interclub, tournoi, cours...)."
        else:
            # Vérifie les limites hebdomadaires (dimanche au samedi)
            debut_semaine = date_obj - timedelta(days=date_obj.weekday() + 1)
            fin_semaine   = debut_semaine + timedelta(days=6)

            reservations_semaine = Reservation.objects.filter(
                membre=membre,
                date__gte=debut_semaine,
                date__lte=fin_semaine
            )

            # Calcule les heures déjà réservées cette semaine
            heures_simple = sum(1 for r in reservations_semaine if r.type_jeu == 'simple')
            heures_double = sum(2 for r in reservations_semaine if r.type_jeu == 'double')

            if type_jeu == 'simple' and heures_simple >= 2:
                erreur = "Vous avez atteint votre limite de 2h de simple par semaine."
            elif type_jeu == 'double' and heures_double >= 4:
                erreur = "Vous avez atteint votre limite de 4h de double par semaine."
            else:
                # Crée la réservation
                r = Reservation(
                    membre=membre,
                    terrain=terrain,
                    date=date_obj,
                    heure_debut=heure_obj,
                    type_jeu=type_jeu,
                )
                if partenaire1:
                    r.partenaire1 = Membre.objects.get(pk=partenaire1)
                if type_jeu == 'double':
                    if partenaire2:
                        r.partenaire2 = Membre.objects.get(pk=partenaire2)
                    if partenaire3:
                        r.partenaire3 = Membre.objects.get(pk=partenaire3)
                r.save()
                return redirect('mes_reservations')

    return render(request, 'tennis/faire_reservation.html', {
        'terrains': terrains,
        'membres_actifs': membres_actifs,
        'creneaux': creneaux,
        'erreur': erreur,
    })

# ============================================================
# MODIFIER SON PROFIL
# Un membre peut modifier ses coordonnées et son mot de passe
# ============================================================
def modifier_profil(request):
    if not request.session.get('membre_id'):
        return redirect('login')

    membre  = Membre.objects.get(pk=request.session['membre_id'])
    message = None
    erreur  = None

    if request.method == 'POST':
        # Met à jour les coordonnées
        membre.adresse   = request.POST.get('adresse')
        membre.telephone = request.POST.get('telephone')
        membre.email     = request.POST.get('email')

        # Changement de mot de passe optionnel
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')

        if password1:
            if password1 != password2:
                erreur = "Les mots de passe ne correspondent pas."
            elif len(password1) < 6:
                erreur = "Le mot de passe doit contenir au moins 6 caractères."
            else:
                membre.password = make_password(password1)

        if not erreur:
            membre.save()
            message = "Vos coordonnées ont été mises à jour."

    return render(request, 'tennis/modifier_profil.html', {
        'membre': membre,
        'message': message,
        'erreur': erreur,
    })

# ============================================================
# LISTE DES TERRAINS AVEC PLANNING
# Affiche les réservations et blocages pour une date donnée
# ============================================================
def liste_terrains(request):
    if not request.session.get('membre_id'):
        return redirect('login')

    from datetime import date
    date_selectionnee = request.GET.get('date', date.today().strftime('%Y-%m-%d'))
    date_obj = datetime.strptime(date_selectionnee, '%Y-%m-%d').date()

    terrains = Terrain.objects.all()
    creneaux = [f"{h:02d}:00" for h in range(9, 22)]

    # Construit le planning heure par heure pour chaque terrain
    planning = []
    for terrain in terrains:
        reservations = Reservation.objects.filter(
            terrain=terrain, date=date_obj
        ).select_related('membre')

        blocages = BlocageTerrain.objects.filter(
            terrain=terrain, date=date_obj
        )

        slots = []
        for creneau in creneaux:
            heure = datetime.strptime(creneau, '%H:%M').time()

            # Cherche une réservation pour ce créneau
            reservation = next((r for r in reservations if r.heure_debut == heure), None)

            # Cherche un blocage couvrant ce créneau
            bloque = next((b for b in blocages
                          if b.heure_debut <= heure < b.heure_fin), None)

            slots.append({
                'heure': creneau,
                'reservation': reservation,
                'bloque': bloque,
            })

        planning.append({
            'terrain': terrain,
            'slots': slots,
        })

    return render(request, 'tennis/liste_terrains.html', {
        'planning': planning,
        'creneaux': creneaux,
        'date_selectionnee': date_selectionnee,
    })

# ============================================================
# DASHBOARD ADMIN
# Vue principale de l'administration : membres et terrains
# ============================================================
@admin_required
def admin_dashboard(request):
    membres  = Membre.objects.all().order_by('nom', 'prenom')
    terrains = Terrain.objects.all()
    return render(request, 'tennis/admin/dashboard.html', {
        'membres': membres,
        'terrains': terrains,
    })

# ============================================================
# ACTIVER / DÉSACTIVER UN MEMBRE
# Active ou désactive l'ordre de cotisation d'un membre
# ============================================================
@admin_required
def toggle_membre(request, numero):
    membre       = Membre.objects.get(pk=numero)
    membre.actif = not membre.actif
    membre.save()
    return redirect('admin_dashboard')

# ============================================================
# AJOUTER UN MEMBRE (admin)
# Le mot de passe temporaire est 'password123'
# Le membre devra le changer à sa première connexion
# ============================================================
@admin_required
def ajouter_membre(request):
    erreur = None
    if request.method == 'POST':
        try:
            m = Membre(
                numero_affiliation=request.POST.get('numero_affiliation'),
                nom=request.POST.get('nom'),
                prenom=request.POST.get('prenom'),
                adresse=request.POST.get('adresse'),
                telephone=request.POST.get('telephone'),
                email=request.POST.get('email'),
                date_naissance=request.POST.get('date_naissance'),
                sexe=request.POST.get('sexe'),
                classement=request.POST.get('classement'),
                password=make_password('password123'),
                actif=False,
                premiere_connexion=True
            )
            m.save()
            return redirect('admin_dashboard')
        except Exception as e:
            erreur = str(e)

    return render(request, 'tennis/admin/ajouter_membre.html', {
        'classements': Membre.CLASSEMENTS,
        'erreur': erreur,
    })

# ============================================================
# SUPPRIMER UN MEMBRE (admin)
# ============================================================
@admin_required
def supprimer_membre(request, numero):
    membre = Membre.objects.get(pk=numero)
    membre.delete()
    return redirect('admin_dashboard')

# ============================================================
# MODIFIER UN MEMBRE (admin)
# L'admin peut modifier les coordonnées et le classement
# ============================================================
@admin_required
def modifier_membre(request, numero):
    membre  = Membre.objects.get(pk=numero)
    erreur  = None
    message = None

    if request.method == 'POST':
        membre.nom        = request.POST.get('nom')
        membre.prenom     = request.POST.get('prenom')
        membre.adresse    = request.POST.get('adresse')
        membre.telephone  = request.POST.get('telephone')
        membre.email      = request.POST.get('email')
        membre.classement = request.POST.get('classement')
        membre.save()
        message = "Membre modifié avec succès."

    return render(request, 'tennis/admin/modifier_membre.html', {
        'membre': membre,
        'classements': Membre.CLASSEMENTS,
        'message': message,
        'erreur': erreur,
    })

# ============================================================
# AJOUTER UN TERRAIN (admin)
# ============================================================
@admin_required
def ajouter_terrain(request):
    if request.method == 'POST':
        numero = request.POST.get('numero')
        Terrain(numero=numero).save()
    return redirect('admin_dashboard')

# ============================================================
# SUPPRIMER UN TERRAIN (admin)
# ============================================================
@admin_required
def supprimer_terrain(request, numero):
    Terrain.objects.get(pk=numero).delete()
    return redirect('admin_dashboard')

# ============================================================
# BLOQUER UN TERRAIN (admin)
# Pour interclub, tournoi, cours, travaux...
# ============================================================
@admin_required
def bloquer_terrain(request):
    terrains = Terrain.objects.all()
    erreur   = None

    if request.method == 'POST':
        terrain_id  = request.POST.get('terrain')
        date        = request.POST.get('date')
        heure_debut = request.POST.get('heure_debut')
        heure_fin   = request.POST.get('heure_fin')
        motif       = request.POST.get('motif')

        try:
            BlocageTerrain(
                terrain=Terrain.objects.get(pk=terrain_id),
                date=date,
                heure_debut=heure_debut,
                heure_fin=heure_fin,
                motif=motif
            ).save()
            return redirect('admin_dashboard')
        except Exception as e:
            erreur = str(e)

    return render(request, 'tennis/admin/bloquer_terrain.html', {
        'terrains': terrains,
        'erreur': erreur,
    })

# ============================================================
# RÉSERVER POUR UN MEMBRE (admin)
# L'admin peut réserver un terrain pour n'importe quel membre
# ============================================================
@admin_required
def admin_reserver(request):
    terrains = Terrain.objects.all()
    membres  = Membre.objects.filter(actif=True)
    creneaux = [f"{h:02d}:00" for h in range(9, 22)]
    erreur   = None

    if request.method == 'POST':
        terrain_id = request.POST.get('terrain')
        membre_id  = request.POST.get('membre')
        date       = request.POST.get('date')
        heure      = request.POST.get('heure')
        type_jeu   = request.POST.get('type_jeu')

        terrain   = Terrain.objects.get(pk=terrain_id)
        membre    = Membre.objects.get(pk=membre_id)
        date_obj  = datetime.strptime(date, '%Y-%m-%d').date()
        heure_obj = datetime.strptime(heure, '%H:%M').time()

        # Vérifie que le terrain n'est pas déjà réservé
        deja_reserve = Reservation.objects.filter(
            terrain=terrain, date=date_obj, heure_debut=heure_obj
        ).exists()

        # Vérifie que le terrain n'est pas bloqué
        terrain_bloque = BlocageTerrain.objects.filter(
            terrain=terrain,
            date=date_obj,
            heure_debut__lte=heure_obj,
            heure_fin__gt=heure_obj
        ).exists()

        if deja_reserve:
            erreur = "Ce terrain est déjà réservé à cette heure."
        elif terrain_bloque:
            erreur = "Ce terrain est bloqué à cette heure."
        else:
            Reservation(
                membre=membre,
                terrain=terrain,
                date=date_obj,
                heure_debut=heure_obj,
                type_jeu=type_jeu,
            ).save()
            return redirect('admin_dashboard')

    return render(request, 'tennis/admin/admin_reserver.html', {
        'terrains': terrains,
        'membres': membres,
        'creneaux': creneaux,
        'erreur': erreur,
    })

# ============================================================
# GESTION DES ERREURS
# Pages d'erreur personnalisées
# ============================================================
def erreur_404(request, exception):
    return render(request, '404.html', status=404)

def erreur_500(request):
    return render(request, '500.html', status=500)

# ============================================================
# AJAX : vérifie la disponibilité d'un terrain
# Retourne un JSON : {"disponible": true/false, "message": "..."}
# ============================================================
def verifier_disponibilite(request):
    if not request.session.get('membre_id'):
        return JsonResponse({'erreur': 'Non connecté'}, status=403)

    terrain_id = request.GET.get('terrain')
    date       = request.GET.get('date')
    heure      = request.GET.get('heure')

    if not all([terrain_id, date, heure]):
        return JsonResponse({'disponible': None, 'message': ''})

    try:
        terrain   = Terrain.objects.get(pk=terrain_id)
        date_obj  = datetime.strptime(date, '%Y-%m-%d').date()
        heure_obj = datetime.strptime(heure, '%H:%M').time()

        # Vérifie si déjà réservé
        deja_reserve = Reservation.objects.filter(
            terrain=terrain, date=date_obj, heure_debut=heure_obj
        ).exists()

        # Vérifie si bloqué par un admin
        terrain_bloque = BlocageTerrain.objects.filter(
            terrain=terrain,
            date=date_obj,
            heure_debut__lte=heure_obj,
            heure_fin__gt=heure_obj
        ).exists()

        if deja_reserve:
            return JsonResponse({
                'disponible': False,
                'message': ' Ce terrain est déjà réservé à cette heure.'
            })
        elif terrain_bloque:
            return JsonResponse({
                'disponible': False,
                'message': ' Ce terrain est bloqué à cette heure (interclub, tournoi, cours...).'
            })
        else:
            return JsonResponse({
                'disponible': True,
                'message': ' Ce terrain est disponible !'
            })

    except Exception as e:
        return JsonResponse({'disponible': None, 'message': str(e)})
    

# ============================================================
# GOOGLE LOGIN — Redirection vers Google
# ============================================================
GOOGLE_AUTH_URL = 'https://accounts.google.com/o/oauth2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO_URL = 'https://www.googleapis.com/oauth2/v2/userinfo'
GOOGLE_SCOPE = ['openid', 'email', 'profile']

def google_login(request):
    from django.conf import settings
    oauth = OAuth2Session(
        settings.GOOGLE_CLIENT_ID,
        redirect_uri=settings.GOOGLE_REDIRECT_URI,
        scope=GOOGLE_SCOPE
    )
    authorization_url, state = oauth.authorization_url(GOOGLE_AUTH_URL)
    request.session['oauth_state'] = state
    return redirect(authorization_url)

# ============================================================
# GOOGLE CALLBACK — Retour après authentification Google
# ============================================================

def google_callback(request):
    from django.conf import settings
    import os
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'  # Pour le dev local en HTTP

    oauth = OAuth2Session(
        settings.GOOGLE_CLIENT_ID,
        redirect_uri=settings.GOOGLE_REDIRECT_URI,
        state=request.session.get('oauth_state')
    )
    token = oauth.fetch_token(
        GOOGLE_TOKEN_URL,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        authorization_response=request.build_absolute_uri()
    )
    response  = oauth.get(GOOGLE_USERINFO_URL)
    user_info = response.json()

    email  = user_info.get('email')
    nom    = user_info.get('family_name', '')
    prenom = user_info.get('given_name', '')

    try:
        membre = Membre.objects.get(email=email)

        if not membre.actif:
            return render(request, 'tennis/login.html', {
                'erreur': 'Votre compte n\'est pas actif. Contactez un administrateur.'
            })

        request.session['membre_id']  = membre.numero_affiliation
        request.session['membre_nom'] = f"{prenom} {nom}"
        request.session['is_admin']   = Administrateur.objects.filter(pk=membre.numero_affiliation).exists()

        if membre.premiere_connexion:
            return redirect('changer_password')

        return redirect('accueil')

    except Membre.DoesNotExist:
        return render(request, 'tennis/login.html', {
            'erreur': 'Aucun membre du club n\'est associé à ce compte Google. Contactez un administrateur.'
        })