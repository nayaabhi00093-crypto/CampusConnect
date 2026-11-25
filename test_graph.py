
from graph import StudentGraph

network = StudentGraph()

network.add_student("Abhi")
network.add_student("Gautham")
network.add_student("Anoushka")
network.add_student("Aradhya")

network.add_connection("Abhi", "Gautham")
network.add_connection("Gautham", "Anoushka")
network.add_connection("Anoushka", "Aradhya")


print("Student Network:")
print(network.adjacency_list)


print("Shortest Chain:")
print(network.shortest_chain("Abhi", "Aradhya"))


print("\n--- CONNECTION REQUEST TEST ---")


print("Request sent:",
      network.send_request("Abhi", "Gautham"))


print("Pending requests:", network.pending_requests)


print("Request accepted:",
      network.accept_request("Abhi", "Gautham"))


print("Abhi's connections:",
      network.get_connections("Abhi"))


print("Request sent:",
      network.send_request("Gautham", "Aradhya"))

print("Request rejected:",
      network.reject_request("Gautham", "Aradhya"))


print("Request sent:",
      network.send_request("Aradhya", "Abhi"))

print("Request cancelled:",
      network.cancel_request("Aradhya", "Abhi"))


print("\n--- PEOPLE YOU MAY KNOW ---")

print("Abhi's mutual connections with Anoushka:",
      network.mutual_connections("Abhi", "Anoushka"))

print("Suggestions for Abhi:",
      network.suggest_connections("Abhi"))


print("\n--- CONNECTION DEGREES ---")

print("Abhi to Gautham:",
      network.connection_degree("Abhi", "Gautham"))

print("Abhi to Anoushka:",
      network.connection_degree("Abhi", "Anoushka"))

print("Abhi to Aradhya:",
      network.connection_degree("Abhi", "Aradhya"))


