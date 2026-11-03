import sqlite3
from premier_league.database import db_connection

# Карта гражданств для игроков состава
KNOWN_NATIONALITIES = {
    # Arsenal
    ("David", "Raya"): "Spain",
    ("Illan", "Meslier"): "France",
    ("Kepa", "Arrizabalaga"): "Spain",
    ("Ben", "White"): "England",
    ("William", "Saliba"): "France",
    ("Gabriel", "Magalhães"): "Brazil",
    ("Cristhian", "Mosquera"): "Spain",
    ("Myles", "Lewis-Skelly"): "England",
    ("Piero", "Hincapié"): "Ecuador",
    ("Riccardo", "Calafiori"): "Italy",
    ("Ezri", "Konsa"): "England",
    ("Jurriën", "Timber"): "Netherlands",
    ("Bruno", "Guimarães"): "Brazil",
    ("Bukayo", "Saka"): "England",
    ("Declan", "Rice"): "England",
    ("Kai", "Havertz"): "Germany",
    ("Martín", "Zubimendi"): "Spain",
    ("Martin", "Ødegaard"): "Norway",
    ("Mikel", "Merino"): "Spain",
    ("Noni", "Madueke"): "England",
    ("Christos", "Tzolis"): "Greece",
    ("Eberechi", "Eze"): "England",
    ("Viktor", "Gyökeres"): "Sweden",
    # Aston Villa
    ("Zion", "Suzuki"): "Japan",
    ("Marco", "Bizot"): "Netherlands",
    ("Aaron", "Wan-Bissaka"): "DR Congo",
    ("Victor", "Lindelöf"): "Sweden",
    ("Ian", "Maatsen"): "Netherlands",
    ("Lamare", "Bogarde"): "Netherlands",
    ("Matteo", "Ruggeri"): "Italy",
    ("Matty", "Cash"): "Poland",
    ("Pau", "Torres"): "Spain",
    ("Tyrone", "Mings"): "England",
    ("Taylor", "Harwood-Bellis"): "England",
    ("Alejandro", "Garnacho"): "Argentina",
    ("Amadou", "Onana"): "Belgium",
    ("Boubacar", "Kamara"): "France",
    ("John", "McGinn"): "Scotland",
    ("João", "Gomes"): "Brazil",
    ("Leon", "Goretzka"): "Germany",
    ("Ross", "Barkley"): "England",
    ("Emiliano", "Buendía"): "Argentina",
    ("Nicolas", "Jackson"): "Senegal",
    ("Tammy", "Abraham"): "England",
    # Bournemouth
    ("Đorđe", "Petrović"): "Serbia",
    ("Michele", "Di Gregorio"): "Italy",
    ("Fraser", "Forster"): "England",
    ("Adam", "Smith"): "England",
    ("Adrien", "Truffert"): "France",
    ("António", "Silva"): "Portugal",
    ("Bafodé", "Diakité"): "France",
    ("Max", "Aarons"): "England",
    ("Julián", "Araujo"): "Mexico",
    ("Julio", "Soler"): "Argentina",
    ("Alex", "Scott"): "England",
    ("Amine", "Adli"): "Morocco",
    ("Ben", "Doak"): "Scotland",
    ("Justin", "Kluivert"): "Netherlands",
    ("David", "Brooks"): "Wales",
    ("Lewis", "Cook"): "England",
    ("Marcus", "Tavernier"): "England",
    ("Ryan", "Christie"): "Scotland",
    ("Tyler", "Adams"): "United States",
    ("Evanilson", "Lima"): "Brazil",
    # Brighton
    ("Bart", "Verbruggen"): "Netherlands",
    ("Jason", "Steele"): "England",
    ("Lewis", "Dunk"): "England",
    ("Maxim", "De Cuyper"): "Belgium",
    ("Olivier", "Boscagli"): "France",
    ("Pascal", "Struijk"): "Netherlands",
    ("Ferdi", "Kadıoğlu"): "Turkey",
    ("Jack", "Hinshelwood"): "England",
    ("Kaoru", "Mitoma"): "Japan",
    ("Mats", "Wieffer"): "Netherlands",
    ("Matt", "O'Riley"): "Denmark",
    ("Pascal", "Groß"): "Germany",
    ("Yankuba", "Minteh"): "Gambia",
    ("Yasin", "Ayari"): "Sweden",
    ("Georginio", "Rutter"): "France",
    ("Evan", "Ferguson"): "Ireland",
    # Brentford
    ("Caoimhín", "Kelleher"): "Ireland",
    ("Aaron", "Hickey"): "Scotland",
    ("Kristoffer", "Ajer"): "Norway",
    ("Michael", "Kayode"): "Italy",
    ("Nathan", "Collins"): "Ireland",
    ("Rico", "Henry"): "England",
    ("Sepp", "van den Berg"): "Netherlands",
    ("Vitaly", "Janelt"): "Germany",
    ("Kevin", "Schade"): "Germany",
    ("Keane", "Lewis-Potter"): "England",
    ("Mathias", "Jensen"): "Denmark",
    ("Mikkel", "Damsgaard"): "Denmark",
    ("Fábio", "Carvalho"): "Portugal",
    ("Dango", "Ouattara"): "Burkina Faso",
    ("Igor", "Thiago"): "Brazil",
    ("Callum", "Wilson"): "England",
    # Liverpool
    ("Alisson", "Becker"): "Brazil",
    ("Giorgi", "Mamardashvili"): "Georgia",
    ("Virgil", "van Dijk"): "Netherlands",
    ("Jeremie", "Frimpong"): "Netherlands",
    ("Joe", "Gomez"): "England",
    ("Conor", "Bradley"): "Northern Ireland",
    ("Kostas", "Tsimikas"): "Greece",
    ("Milos", "Kerkez"): "Hungary",
    ("Ronald", "Araújo"): "Uruguay",
    ("Alexis", "Mac Allister"): "Argentina",
    ("Bradley", "Barcola"): "France",
    ("Wataru", "Endo"): "Japan",
    ("Dominik", "Szoboszlai"): "Hungary",
    ("Cody", "Gakpo"): "Netherlands",
    ("Ryan", "Gravenberch"): "Netherlands",
    ("Federico", "Chiesa"): "Italy",
    ("Florian", "Wirtz"): "Germany",
    ("Alexander", "Isak"): "Sweden",
    ("Hugo", "Ekitiké"): "France",
    # Man City
    ("Gianluigi", "Donnarumma"): "Italy",
    ("Gerónimo", "Rulli"): "Argentina",
    ("Abdukodir", "Khusanov"): "Uzbekistan",
    ("Joško", "Gvardiol"): "Croatia",
    ("Marc", "Guéhi"): "England",
    ("Rayan", "Aït-Nouri"): "Algeria",
    ("Rico", "Lewis"): "England",
    ("Rúben", "Dias"): "Portugal",
    ("Antoine", "Semenyo"): "Ghana",
    ("Jérémy", "Doku"): "Belgium",
    ("Mateo", "Kovačić"): "Croatia",
    ("Matheus", "Nunes"): "Portugal",
    ("Rayan", "Cherki"): "France",
    ("Phil", "Foden"): "England",
    ("Elliot", "Anderson"): "Scotland",
    ("Enzo", "Fernández"): "Argentina",
    ("Erling", "Haaland"): "Norway",
    # Man United
    ("Senne", "Lammens"): "Belgium",
    ("Diogo", "Dalot"): "Portugal",
    ("Leny", "Yoro"): "France",
    ("Lisandro", "Martínez"): "Argentina",
    ("Luke", "Shaw"): "England",
    ("Matthijs", "de Ligt"): "Netherlands",
    ("Noussair", "Mazraoui"): "Morocco",
    ("Patrick", "Dorgu"): "Denmark",
    ("Harry", "Maguire"): "England",
    ("Amad", "Diallo"): "Ivory Coast",
    ("Andrey", "Santos"): "Brazil",
    ("Bryan", "Mbeumo"): "Cameroon",
    ("Bruno", "Fernandes"): "Portugal",
    ("Kobbie", "Mainoo"): "England",
    ("Manuel", "Ugarte"): "Uruguay",
    ("Mason", "Mount"): "England",
    ("Youri", "Tielemans"): "Belgium",
    ("Benjamin", "Šeško"): "Slovenia",
    ("Joshua", "Zirkzee"): "Netherlands",
    ("Marcus", "Rashford"): "England",
    ("Matheus", "Cunha"): "Brazil",
    # Tottenham
    ("Martin", "Dúbravka"): "Slovakia",
    ("Ben", "Davies"): "Wales",
    ("Destiny", "Udogie"): "Italy",
    ("Micky", "van de Ven"): "Netherlands",
    ("Pedro", "Porro"): "Spain",
    ("Andrew", "Robertson"): "Scotland",
    ("Archie", "Gray"): "England",
    ("Dejan", "Kulusevski"): "Sweden",
    ("James", "Maddison"): "England",
    ("Conor", "Gallagher"): "England",
    ("Lucas", "Bergvall"): "Sweden",
    ("Mykhailo", "Mudryk"): "Ukraine",
    ("Mohammed", "Kudus"): "Ghana",
    ("Rodrigo", "Bentancur"): "Uruguay",
    ("Savinho", "Moreira"): "Brazil",
    ("Sandro", "Tonali"): "Italy",
    ("Xavi", "Simons"): "Netherlands",
    ("Dominic", "Solanke"): "England",
    ("Richarlison", "de Andrade"): "Brazil",
    # Chelsea
    ("Emiliano", "Martínez"): "Argentina",
    ("Valentín", "Barco"): "Argentina",
    ("Jorrel", "Hato"): "Netherlands",
    ("Levi", "Colwill"): "England",
    ("Maxence", "Lacroix"): "France",
    ("Malo", "Gusto"): "France",
    ("Reece", "James"): "England",
    ("Wesley", "Fofana"): "France",
    ("Jordan", "Henderson"): "England",
    ("Cole", "Palmer"): "England",
    ("Moisés", "Caicedo"): "Ecuador",
    ("Morgan", "Rogers"): "England",
    ("Pedro", "Neto"): "Portugal",
    ("Roméo", "Lavia"): "Belgium",
    ("Danny", "Welbeck"): "England",
    ("João", "Pedro"): "Brazil",
    ("Estêvão", "Willian"): "Brazil",
    # Everton
    ("Jordan", "Pickford"): "England",
    ("Vitalii", "Mykolenko"): "Ukraine",
    ("Jake", "O'Brien"): "Ireland",
    ("James", "Tarkowski"): "England",
    ("Jarrad", "Branthwaite"): "England",
    ("Brennan", "Johnson"): "Wales",
    ("Jack", "Grealish"): "England",
    ("Carlos", "Alcaraz"): "Argentina",
    ("Kiernan", "Dewsbury-Hall"): "England",
    ("Christian", "Nørgaard"): "Denmark",
}


def update_nationalities():
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, first_name, last_name, nationality FROM players;")
        players = cursor.fetchall()

        updated_count = 0
        for p in players:
            p_id = p["id"]
            fn = p["first_name"]
            ln = p["last_name"]
            current_nat = p["nationality"]

            target_nat = KNOWN_NATIONALITIES.get((fn, ln))

            # Если для игрока нет явного соответствия, но у него стоит Unknown:
            if not target_nat and (not current_nat or current_nat == "Unknown"):
                target_nat = "England"

            if target_nat and target_nat != current_nat:
                cursor.execute(
                    "UPDATE players SET nationality = ? WHERE id = ?;", (target_nat, p_id)
                )
                updated_count += 1

        print(f"Готово! Обновлено гражданств: {updated_count} из {len(players)} игроков.")


if __name__ == "__main__":
    update_nationalities()
