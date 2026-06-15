from django.db import models
from django.core.validators import RegexValidator

# ============================================================
# SAISON
# Représente une saison sportive (janvier à décembre)
# ============================================================
class Saison(models.Model):
    annee = models.IntegerField(primary_key=True)  # ex: 2026

    def __str__(self):
        return f"Saison {self.annee}"

# ============================================================
# MEMBRE (classe de base)
# Un membre est identifié par son numéro AFT (7 chiffres)
# Il doit être actif (en ordre de cotisation) pour réserver
# ============================================================
class Membre(models.Model):
    # Numéro AFT : 7 chiffres, ne commence pas par 0
    numero_affiliation = models.CharField(
        max_length=7,
        primary_key=True,
        validators=[RegexValidator(
            r'^[1-9][0-9]{6}$',
            'Le numéro doit contenir 7 chiffres et ne pas commencer par 0'
        )]
    )
    nom            = models.CharField(max_length=50)
    prenom         = models.CharField(max_length=50)
    adresse        = models.CharField(max_length=100)
    telephone      = models.CharField(max_length=20)
    email          = models.EmailField()
    date_naissance = models.DateField()

    SEXE_CHOICES = [('M', 'Masculin'), ('F', 'Féminin')]
    sexe = models.CharField(max_length=1, choices=SEXE_CHOICES)

    # Classements possibles selon l'AFT
    CLASSEMENTS = [
        ('A', 'A'), ('B-15.4', 'B-15.4'), ('B-15.2', 'B-15.2'),
        ('B-15.1', 'B-15.1'), ('B15', 'B15'), ('B-4/6', 'B-4/6'),
        ('B-2/6', 'B-2/6'), ('B0', 'B0'), ('B+2/6', 'B+2/6'),
        ('B+4/6', 'B+4/6'), ('C15', 'C15'), ('C15.1', 'C15.1'),
        ('C15.2', 'C15.2'), ('C15.3', 'C15.3'), ('C15.4', 'C15.4'),
        ('C30', 'C30'), ('C30.1', 'C30.1'), ('C30.2', 'C30.2'),
        ('C30.3', 'C30.3'), ('C30.4', 'C30.4'), ('C30.5', 'C30.5'),
        ('N.C', 'N.C'),
    ]
    classement = models.CharField(max_length=10, choices=CLASSEMENTS)

    # Mot de passe hashé
    password = models.CharField(max_length=255)

    # True si le membre est en ordre de cotisation pour la saison courante
    actif = models.BooleanField(default=False)

    # True si c'est la première connexion → doit changer son mot de passe
    premiere_connexion = models.BooleanField(default=True)

    # Attribut de classe pour identifier le type de profil
    person_type = 'membre'

    def __str__(self):
        return f"{self.nom} {self.prenom} ({self.numero_affiliation})"

    def get_categories(self):
        """
        Calcule les catégories du membre selon son âge et son sexe.
        Une dame de 46 ans appartient à : Dames, Dames 25, Dames 35, Dames 45.
        """
        from datetime import date
        today = date.today()
        age = today.year - self.date_naissance.year - (
            (today.month, today.day) < 
            (self.date_naissance.month, self.date_naissance.day)
        )
        categories = []

        if self.sexe == 'F':
            if age <= 9:
                categories.append('JF/JG -9ans')
            elif age <= 11:
                categories.append('JF-11 ans')
            elif age <= 13:
                categories.append('JF-13 ans')
            elif age <= 15:
                categories.append('JF-15 ans')
            elif age <= 17:
                categories.append('JF-17 ans')
            if age >= 16:
                categories.append('Dames')
            if age >= 25:
                categories.append('Dames 25')
            if age >= 35:
                categories.append('Dames 35')
            if age >= 45:
                categories.append('Dames 45')
            if age >= 55:
                categories.append('Dames 55')
        else:  # Masculin
            if age <= 9:
                categories.append('JF/JG -9ans')
            elif age <= 11:
                categories.append('JG-11 ans')
            elif age <= 13:
                categories.append('JG-13 ans')
            elif age <= 15:
                categories.append('JG-15 ans')
            elif age <= 17:
                categories.append('JG-17 ans')
            if age >= 16:
                categories.append('Messieurs')
            if age >= 35:
                categories.append('Messieurs 35')
            if age >= 55:
                categories.append('Messieurs 55')
            if age >= 60:
                categories.append('Messieurs 60')
            if age >= 65:
                categories.append('Messieurs 65')
            if age >= 70:
                categories.append('Messieurs 70')

        return categories


# ============================================================
# ADMINISTRATEUR (hérite de Membre)
# A les mêmes fonctionnalités qu'un membre + gestion du club
# ============================================================
class Administrateur(Membre):
    person_type = 'administrateur'

    class Meta:
        verbose_name = "Administrateur"


# ============================================================
# TERRAIN
# Identifié par un numéro unique
# ============================================================
class Terrain(models.Model):
    numero = models.IntegerField(primary_key=True)

    def __str__(self):
        return f"Terrain {self.numero}"


# ============================================================
# RESERVATION
# Un membre réserve un terrain pour 1h (simple) ou 2h (double)
# Limites : 2h/semaine en simple, 4h/semaine en double
# ============================================================
class Reservation(models.Model):
    TYPE_CHOICES = [('simple', 'Simple'), ('double', 'Double')]

    # Membre qui fait la réservation
    membre  = models.ForeignKey(Membre, on_delete=models.CASCADE, related_name='reservations')
    terrain = models.ForeignKey(Terrain, on_delete=models.CASCADE)
    date    = models.DateField()

    # Heure de début entre 9h et 22h
    heure_debut = models.TimeField()
    type_jeu    = models.CharField(max_length=10, choices=TYPE_CHOICES)

    # Partenaires (membres actifs du club)
    partenaire1 = models.ForeignKey(Membre, on_delete=models.SET_NULL, null=True, blank=True, related_name='reservations_partenaire1')
    partenaire2 = models.ForeignKey(Membre, on_delete=models.SET_NULL, null=True, blank=True, related_name='reservations_partenaire2')
    partenaire3 = models.ForeignKey(Membre, on_delete=models.SET_NULL, null=True, blank=True, related_name='reservations_partenaire3')

    def __str__(self):
        return f"Terrain {self.terrain} - {self.date} {self.heure_debut} ({self.type_jeu})"


# ============================================================
# BLOCAGE TERRAIN
# Un admin peut bloquer un terrain pour interclub, tournoi, cours...
# ============================================================
class BlocageTerrain(models.Model):
    terrain     = models.ForeignKey(Terrain, on_delete=models.CASCADE)
    date        = models.DateField()
    heure_debut = models.TimeField()
    heure_fin   = models.TimeField()

    # Motif du blocage : interclub, tournoi, cours, travaux...
    motif = models.CharField(max_length=100)

    def __str__(self):
        return f"Blocage terrain {self.terrain} - {self.date} ({self.motif})"