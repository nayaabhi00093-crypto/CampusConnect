
from collections import deque


class StudentGraph:

    def __init__(self):
        self.adjacency_list = {}
        self.pending_requests = set()

    def add_student(self, username):
        if username not in self.adjacency_list:
            self.adjacency_list[username] = set()

    def add_connection(self, student1, student2):

        if student1 == student2:
            return False

        if student1 not in self.adjacency_list:
            return False

        if student2 not in self.adjacency_list:
            return False

        self.adjacency_list[student1].add(student2)
        self.adjacency_list[student2].add(student1)

        return True

    def get_connections(self, username):
        return self.adjacency_list.get(username, set())

    def mutual_connections(self, student1, student2):

        connections1 = self.get_connections(student1)
        connections2 = self.get_connections(student2)

        return connections1.intersection(connections2)

    def shortest_chain(self, start, destination):

        if start not in self.adjacency_list:
            return None

        if destination not in self.adjacency_list:
            return None

        queue = deque([[start]])
        visited = {start}

        while queue:

            path = queue.popleft()
            current = path[-1]

            if current == destination:
                return path

            for neighbour in self.adjacency_list[current]:

                if neighbour not in visited:
                    visited.add(neighbour)
                    queue.append(path + [neighbour])

        return None

    def send_request(self, sender, receiver):

        if sender == receiver:
            return False

        if sender not in self.adjacency_list:
            return False

        if receiver not in self.adjacency_list:
            return False

        if receiver in self.adjacency_list[sender]:
            return False

        if (sender, receiver) in self.pending_requests:
            return False

        if (receiver, sender) in self.pending_requests:
            return False

        self.pending_requests.add((sender, receiver))

        return True

    def accept_request(self, sender, receiver):

        if (sender, receiver) not in self.pending_requests:
            return False

        self.pending_requests.remove((sender, receiver))

        return self.add_connection(sender, receiver)

    def reject_request(self, sender, receiver):

        if (sender, receiver) not in self.pending_requests:
            return False

        self.pending_requests.remove((sender, receiver))

        return True

    def cancel_request(self, sender, receiver):

        if (sender, receiver) not in self.pending_requests:
            return False

        self.pending_requests.remove((sender, receiver))

        return True

    def suggest_connections(self, username):

        if username not in self.adjacency_list:
            return []

        suggestions = []

        for student in self.adjacency_list:

            if student == username:
                continue

            if student in self.adjacency_list[username]:
                continue

            mutual = self.mutual_connections(username, student)

            if len(mutual) > 0:
                suggestions.append((student, len(mutual)))

        suggestions.sort(key=lambda x: x[1], reverse=True)

        return suggestions

    def connection_degree(self, start, destination):

        path = self.shortest_chain(start, destination)

        if path is None:
            return None

        return len(path) - 1


def load_graph_from_database():

    import database

    graph = StudentGraph()

    students = database.get_all_students()

    for student in students:
        graph.add_student(student)

    connections = database.get_all_connections()

    for student1, student2 in connections:
        graph.add_connection(student1, student2)

    return graph
